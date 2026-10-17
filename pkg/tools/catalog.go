package tools

// Catálogo compacto de tools (eficiencia de tokens en el arranque MCP).
//
// Las 38 tools se publican en `tools/list` con una descripción de 1-2 líneas
// (~25-45 palabras) agrupada en 4 grupos. La ficha completa de 7 secciones
// (contrato cognitivo) NO se pierde: vive en `FullToolDocs` y se sirve bajo
// demanda como Resource MCP (`android://tool/<name>` y `android://tools/<group>`).
//
// Así el payload de arranque (initialize + tools/list) baja de ~11.5k a
// ≤3k tokens sin retirar ninguna tool ni ninguna validación.

// ToolGroups es el orden canónico de los 4 grupos.
var ToolGroups = []string{"state", "ui", "native", "resolve"}

// toolMeta: grupo, resumen (acción + carril) y si es sensible (exige confirm).
type toolMeta struct {
	Group     string
	Summary   string
	Sensitive bool
}

// toolCatalog espeja la tabla declarativa de register.go (mismos 38 nombres).
var toolCatalog = map[string]toolMeta{
	// --- state: lectura de estado (carril nativo/read) ---
	"device_status":   {"state", "estado Jav: scopes/versión/caps/foreground (read).", false},
	"get_foreground":  {"state", "foreground: paquete+activity (read).", false},
	"list_packages":   {"state", "paquetes instalados vía adb host (read).", false},
	"get_battery":     {"state", "batería: nivel/carga/temp/saver (N0).", false},
	"get_memory":      {"state", "RAM disponible/total/low_memory (N0).", false},
	"get_storage":     {"state", "almacenamiento; fine usa Shizuku (N0/N2).", false},
	"get_cpu":         {"state", "núcleos y uso de CPU; fine=N2 (N0/N2).", false},
	"get_device_info": {"state", "hardware sin IDs persistentes (N0).", false},
	"get_audit":       {"state", "audit ring 500 (solo hashes) (admin).", false},

	// --- ui: bucle de decisión sobre la pantalla ---
	"read_screen":   {"ui", "pantalla normalizada + snapshot_id (read).", false},
	"tap_node":      {"ui", "toca node_id+snapshot_id (ui).", false},
	"tap_text":      {"ui", "toca el primer nodo con text (ui).", false},
	"type_text":     {"ui", "REPLACE en campo enfocado; __PASTE__ pega clipboard (ui).", false},
	"scroll":        {"ui", "scroll up/down (ui).", false},
	"press_back":    {"ui", "botón atrás (ui).", false},
	"press_home":    {"ui", "botón home (ui).", false},
	"wait_for_text": {"ui", "espera text y da snapshot (read).", false},
	"open_app":      {"ui", "abre app (Shizuku) + verify fg (ui).", false},
	"close_app":     {"ui", "force-stop + verify salida (shell).", false},
	"screenshot":    {"ui", "captura; FLAG_SECURE→SECURE_SURFACE (read).", false},

	// --- native: APIs de dispositivo / intents ---
	"settings_get":         {"native", "lee ajuste System/Secure/Global (read).", false},
	"settings_put":         {"native", "escribe ajuste System (crítica) (admin).", true},
	"open_url":             {"native", "abre URL (ACTION_VIEW), no envía (intent).", false},
	"send_intent":          {"native", "intent de apertura/pre-relleno (intent).", true},
	"get_clipboard_device": {"native", "clipboard: len/sha256/text≤2048 (jam/shizuku) (read).", false},
	"get_app_usage":        {"native", "foreground agregado top 50 (N1).", false},
	"list_contacts":        {"native", "contactos; forense count+hash (N1).", false},
	"add_contact":          {"native", "alta de contacto (crítica) (N1).", true},
	"list_events":          {"native", "eventos ≤7 días (N1).", false},
	"create_event":         {"native", "crea evento (crítica) (N1).", true},
	"list_notifications":   {"native", "notificaciones activas (N1).", false},
	"reply_notification":   {"native", "responde vía RemoteInput (crítica) (N1).", true},
	"media_state":          {"native", "sesiones multimedia (N1).", false},
	"media_control":        {"native", "play/pause/next/prev; stop crítico (N1).", true},
	"get_location":         {"native", "ubicación: cache o fix (N1).", false},
	"take_photo":           {"native", "foto headless FGS visible (crítica) (N1).", true},
	"adb_shell":            {"native", "shell UID shell Shizuku; grant+denylist (admin).", true},

	// --- resolve: resolver ciego S1 ---
	"resolve_element": {"resolve", "resuelve el elemento S1 de la micro-intención (resolve).", false},
}

// FullToolDocs conserva la ficha completa de 7 secciones por tool (contrato
// cognitivo íntegro). Se sirve bajo demanda por Resource; nunca se pierde.
var FullToolDocs = buildFullToolDocs()

func buildFullToolDocs() map[string]string {
	m := make(map[string]string, len(toolDefs))
	for _, d := range toolDefs {
		m[d.name] = d.desc
	}
	return m
}

// CompactDesc genera la descripción de 1-2 líneas que viaja en tools/list:
// `[<grupo>] <acción y carril>. Retorno: {ok,verified,evidence,hint}.`
// + (si sensible) `Sin confirm: planned:true+preview; exige confirm:true.`
// + `Spec: android://tool/<name>`.
func CompactDesc(name string) string {
	meta := toolCatalog[name]
	s := "[" + meta.Group + "] " + meta.Summary + " Retorno: {ok,verified,evidence,hint}."
	if meta.Sensitive {
		s += " Sin confirm: planned:true+preview; exige confirm:true."
	}
	return s + " Spec: android://tool/" + name
}

// ToolsInGroup devuelve los nombres del grupo en el orden declarado en toolDefs.
func ToolsInGroup(group string) []string {
	var out []string
	for _, d := range toolDefs {
		if toolCatalog[d.name].Group == group {
			out = append(out, d.name)
		}
	}
	return out
}

// GroupOf expone el grupo de una tool (para tests y auditoría).
func GroupOf(name string) string { return toolCatalog[name].Group }

// SensitiveTools es el conjunto de tools que exigen confirm:true.
var SensitiveTools = map[string]bool{}

func init() {
	for name, meta := range toolCatalog {
		if meta.Sensitive {
			SensitiveTools[name] = true
		}
	}
}
