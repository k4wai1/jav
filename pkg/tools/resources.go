package tools

import (
	"context"
	"encoding/json"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	"github.com/k4wai1/jav/pkg/jam"
)

// Resources de lectura + Prompts guía (guía §4, solo diseño allí;
// aquí implementación Go porque mcp-go los soporta limpio:
// AddResource + AddPrompt, sin código a medias).
//
// - Resources: solo lectura, cacheables, sin PII cruda, sin efectos.
//   Llevan stale_after + advertencia canónica: sus ids/resúmenes no
//   son accionables (para actuar, leer por Tool con snapshot_id).
// - Prompts: guías multi-paso que componen Tools; nunca tocan el
//   dispositivo ni exponen shell/coordenadas/atajos sin compuertas.

const staleWarning = "snapshot decorativo — para actuar, lee por Tool y usa su snapshot_id vigente"

// --- Resources ---

func hTelemetry(ctx context.Context, req mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
	c, jerr := jam.Dial()
	if jerr != nil {
		return nil, jerr
	}
	defer c.Close()
	section := func(method string, params map[string]any) map[string]any {
		res, jerr := c.Call(method, params)
		if jerr != nil {
			return map[string]any{"error": jerr.Code, "hint": jam.JamFail(jerr)["hint"]}
		}
		if method == "get_device_info" {
			for _, k := range []string{"imei", "mac", "serial", "android_id"} {
				delete(res, k)
			}
		}
		return res
	}
	doc := map[string]any{
		"scopes":       c.Scopes,
		"app_version":  c.AppVersion,
		"battery":      section("get_battery", nil),
		"memory":       section("get_memory", nil),
		"storage":      section("get_storage", map[string]any{"detail": "basic"}),
		"cpu":          section("get_cpu", map[string]any{"detail": "basic"}),
		"device":       section("get_device_info", nil),
		"stale_after_s": 60,
		"warning":      staleWarning,
	}
	raw, _ := json.Marshal(doc)
	return []mcp.ResourceContents{
		mcp.TextResourceContents{URI: req.Params.URI, MIMEType: "application/json", Text: string(raw)},
	}, nil
}

func hScreenSummary(ctx context.Context, req mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
	env := readScreenState()
	if ok, _ := env["ok"].(bool); !ok {
		ev, _ := env["evidence"].(map[string]any)
		code, _ := ev["code"].(string)
		return nil, &jam.JamError{Code: code, Message: "read_screen falló"}
	}
	ev := env["evidence"].(map[string]any)
	cands, _ := ev["candidates"].([]map[string]any)
	doc := map[string]any{
		"package":         ev["package"],
		"activity":        ev["activity"],
		"candidate_count": len(cands),
		"focused_field":   ev["focused_field"],
		"first_result":    ev["first_result"],
		"node_ids":        "omitidos (no-actionable en este recurso)",
		"stale_after_s":   5,
		"warning":         staleWarning,
	}
	raw, _ := json.Marshal(doc)
	return []mcp.ResourceContents{
		mcp.TextResourceContents{URI: req.Params.URI, MIMEType: "application/json", Text: string(raw)},
	}, nil
}

// --- Prompts (guías; citan la tabla §3, exigen verify/confirm) ---

const promptTroubleshoot = `Diagnostica por carriles, un experimento por vez (nunca auto-reintento):

1. Base: device_status + get_foreground (¿dónde estoy y con qué scopes?).
2. Descarta entorno por carril nativo (get_battery/get_memory/get_storage/get_cpu/get_device_info/settings_get) antes de tocar la UI.
3. UI solo al final: read_screen + wait_for_text (snapshot_id vigente; STALE_SNAPSHOT → re-lee una vez; segundo STALE → UI_UNSTABLE, para e informa).
4. Ante cada fallo sigue su hint literal (STALE_SNAPSHOT, NOT_FOCUSED, SELECTOR_NOT_FOUND, TIMEOUT, ACCESSIBILITY_DISABLED, SHIZUKU_UNAVAILABLE, METHOD_NOT_ALLOWED, SECURE_SURFACE, PAYLOAD_TOO_LARGE, VERIFY_FAILED, CONNECTION_FAILED).
5. Produce informe + próximo experimento único con su verificación (read_screen/wait_for_text). Nunca abras/cierres apps ni cambies ajustes desde el diagnóstico, y no declares causa sin verify.`

const promptNavigateAndCopy = `Flujo genérico de portapapeles multi-pantalla:

1. En la app-origen, toca copiar (tap_node sobre snapshot vigente) y verifica el cambio con read_screen.
2. Read-back en host (dumpsys) o pegado-readback; verifica forma (p. ej. https?://) antes de transportar.
3. Ante CLIPBOARD_EMPTY: copia primero en la app-origen y re-lee; nunca inventes contenido.
4. Inyecta como payload opaco (len+hash en forense, nunca crudo sensible en el plan).
5. Si el destino comunica a terceros, aplica la compuerta crítica: primera llamada planea ({planned:true, preview, hint}), solo ejecuta repitiendo con confirm:true tras aprobación del operador sobre ese preview exacto.`

const promptSendVerified = `Flujo canónico de acción crítica/irreversible:

1. Pre-rellena por intent (send_intent/open_url: como máximo abre editor pre-rellenado, nunca envía solo) o por UI (tap_node/type_text con snapshot_id vigente y foco explícito).
2. La primera llamada planea ({planned:true, preview, hint}): muestra el preview exacto (longitudes/hashes, nunca texto sensible crudo) y espera aprobación del operador.
3. Solo tras aprobación: repite con confirm:true sobre ese preview exacto (nunca reutilices un confirm para un preview distinto).
4. Verifica con lectura posterior (read_screen/wait_for_text) — éxito solo con verify determinista, nunca solo por el decisor — y audita quién confirmó qué.
5. Ante fallo sigue el hint literal; ante duda escala con contexto en vez de improvisar.`

func promptResult(text string) (*mcp.GetPromptResult, error) {
	return &mcp.GetPromptResult{
		Messages: []mcp.PromptMessage{
			{Role: mcp.RoleUser, Content: mcp.TextContent{Type: "text", Text: text}},
		},
	}, nil
}

// RegisterExtras registra los 2 Resources y 3 Prompts de la guía §4.
func RegisterExtras(s *server.MCPServer) {
	s.AddResource(
		mcp.NewResource("android://device/telemetry", "device_telemetry",
			mcp.WithResourceDescription("Agregados lentos sin PII (batería, memoria, almacenamiento basic, cpu basic, dispositivo sin IDs, grants caps). Cacheable ~60 s. Decorativo: para actuar usa Tools."),
			mcp.WithMIMEType("application/json")),
		hTelemetry)
	s.AddResource(
		mcp.NewResource("android://screen/current_summary", "screen_summary",
			mcp.WithResourceDescription("Resumen estabilizado de la pantalla (foreground, conteo, foco como vista, first_result). Sin node_ids accionables. Decorativo: para actuar usa read_screen."),
			mcp.WithMIMEType("application/json")),
		hScreenSummary)
	s.AddPrompt(
		mcp.NewPrompt("troubleshoot_app",
			mcp.WithPromptDescription("Diagnóstico por carril: base, entorno nativo, UI al final + matriz síntoma→código. Produce informe + un experimento, nunca auto-reintento ni mutaciones."),
			mcp.WithArgument("symptom", mcp.ArgumentDescription("Síntoma observado (texto del operador)"))),
		func(ctx context.Context, req mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
			return promptResult(promptTroubleshoot)
		})
	s.AddPrompt(
		mcp.NewPrompt("navigate_and_copy",
			mcp.WithPromptDescription("Copiar multi-pantalla: tocar copiar, read-back, verificar forma, inyectar opaco. Nunca inventa contenido; cita compuerta crítica si el destino comunica a terceros."),
			mcp.WithArgument("goal", mcp.ArgumentDescription("Qué dato copiar y dónde inyectarlo (texto del operador)"))),
		func(ctx context.Context, req mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
			return promptResult(promptNavigateAndCopy)
		})
	s.AddPrompt(
		mcp.NewPrompt("send_verified",
			mcp.WithPromptDescription("Acción crítica: pre-rellenar, preview, confirm:true del operador, ejecutar, verificar, auditar. Nunca ejecuta sin preview aprobado ni reutiliza confirms."),
			mcp.WithArgument("action_kind", mcp.ArgumentDescription("Clase de efecto crítico (mensaje, compra/pago, borrado, cuenta/permiso, foto, ajuste)"))),
		func(ctx context.Context, req mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
			return promptResult(promptSendVerified)
		})
}
