// Harness e2e jav (spec docs/specs/ai-providers.md, tarea @coder §2).
//
// Lanza `jav` stdio como subproceso y recorre las 35 tools contra el
// teléfono + initialize + resources + prompts. Sin keys propias, 100%
// genérico: ningún paquete concreto, ningún literal de dominio.
//
// Seguridad (vinculante):
//   - Env de `.env` sin imprimir valores (solo presente/ausente).
//   - take_photo SOLO planned sin confirm; la variante con confirm exige
//     --confirm-take-photo explícito del operador (por defecto NotRun).
//   - Críticas sin confirm → planned, NUNCA ejecutadas (no se reintenta
//     con confirm:true salvo settings_put reversible documentado abajo).
//   - UI táctica: tap_node/type_text solo dry-run con node_id bogus
//     (SELECTOR_NOT_FOUND antes de tocar el dispositivo); scroll real
//     down (no destructivo); press_back/press_home reales al final del
//     bloque UI (navegación reversible); open_app/close_app solo
//     validación (VALIDATION_ERROR con forma inválida) salvo
//     --real-open-app (settings, documentado).
//   - settings_put: reversible por construcción — se lee el valor previo
//     con settings_get y se escribe EL MISMO valor con confirm:true
//     (no-op); verificación posterior con settings_get. Sin cambio neto.
//   - PII: la tabla solo publica herramienta, resultado, code y
//     latencia_ms. Jamás contenido (nombres, teléfonos, textos, hashes
//     crudos van solo como conteos/códigos).
//
// Salida: tabla markdown a stdout (+ copia en logs/ si existe).
// Exit 0 = tabla completa (los errores de tool son datos, no fallo);
// exit 2 = NO-GO de pre-vuelo (adb/forward/initialize); exit 1 = fallo
// interno del harness.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/client"
	"github.com/mark3labs/mcp-go/mcp"
)

var sensitiveEnv = map[string]bool{
	"JAV_TOKEN": true, "JEV_TOKEN": true,
	"OPENROUTER_API_KEY": true, "TYPESAFE_API_KEY": true,
	"JEV_CERT_FINGERPRINT": true,
}

// row es una fila de la tabla e2e.
type row struct {
	tool    string
	args    string
	result  string // ok | planned | error | dry-run | NotRun
	code    string
	latMs   float64
	note    string
}

func loadEnvFile(path string) {
	f, err := os.Open(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-e2e: sin env-file %s (%v), sigo con entorno heredado\n", path, err)
		return
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		k := strings.TrimSpace(line[:eq])
		v := strings.TrimSpace(line[eq+1:])
		v = strings.Trim(v, `"'`)
		if k == "" {
			continue
		}
		_ = os.Setenv(k, v)
	}
	// Solo presencia, NUNCA valores.
	for _, k := range []string{"JAV_WS_URL", "JAV_TOKEN", "JEV_WS_URL", "JEV_TOKEN", "OPENROUTER_API_KEY", "JEV_MODEL"} {
		st := "ausente"
		if os.Getenv(k) != "" {
			st = "presente"
		}
		if sensitiveEnv[k] {
			st += " (valor oculto)"
		}
		fmt.Fprintf(os.Stderr, "jav-e2e env: %s=%s\n", k, st)
	}
}

func runCmd(name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, name, args...).CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

func main() {
	serial := flag.String("serial", "e03638e5", "serie adb del teléfono")
	envFile := flag.String("env-file", ".env", "fichero env (valores nunca impresos)")
	javBin := flag.String("jav-bin", "", "binario jav (vacío = compilar temporal de ./cmd/jav)")
	confirmPhoto := flag.Bool("confirm-take-photo", false, "permite take_photo con confirm:true (SOLO con aprobación explícita del operador)")
	realOpenApp := flag.Bool("real-open-app", false, "abre settings de verdad (por defecto solo validación)")
	flag.Parse()

	// 1. Env (sin imprimir valores).
	loadEnvFile(*envFile)

	// 2. Pre-vuelo adb.
	fmt.Fprintln(os.Stderr, "jav-e2e pre-vuelo: adb devices")
	devs, err := runCmd("adb", "devices")
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: adb no disponible: %v\n", err)
		os.Exit(2)
	}
	if !strings.Contains(devs, *serial) {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: serie %s no en adb devices\n%s\n", *serial, devs)
		os.Exit(2)
	}
	st, err := runCmd("adb", "-s", *serial, "get-state")
	if err != nil || st != "device" {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: estado %q err %v\n", st, err)
		os.Exit(2)
	}
	fwd, err := runCmd("adb", "-s", *serial, "forward", "tcp:38472", "tcp:38472")
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: forward falló: %v %s\n", err, fwd)
		os.Exit(2)
	}
	fmt.Fprintln(os.Stderr, "jav-e2e pre-vuelo OK: device + forward tcp:38472")

	// 3. Binario jav.
	bin := *javBin
	var tmpBin string
	if bin == "" {
		tmpBin = filepath.Join(os.TempDir(), "jav-e2e-bin")
		fmt.Fprintln(os.Stderr, "jav-e2e: compilando ./cmd/jav →", tmpBin)
		ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
		out, berr := exec.CommandContext(ctx, "go", "build", "-o", tmpBin, "./cmd/jav").CombinedOutput()
		cancel()
		if berr != nil {
			fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: go build falló: %v\n%s\n", berr, out)
			os.Exit(2)
		}
		bin = tmpBin
		defer os.Remove(tmpBin)
	}

	// 4. Cliente stdio + initialize.
	ctx := context.Background()
	mc, err := client.NewStdioMCPClient(bin, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: stdio client: %v\n", err)
		os.Exit(2)
	}
	defer mc.Close()
	if err := mc.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "jav-e2e NO-GO: start: %v\n", err)
		os.Exit(2)
	}
	t0 := time.Now()
	initRes, err := mc.Initialize(ctx, mcp.InitializeRequest{Params: mcp.InitializeParams{
		ProtocolVersion: mcp.LATEST_PROTOCOL_VERSION,
		Capabilities:    mcp.ClientCapabilities{},
		ClientInfo:      mcp.Implementation{Name: "jav-e2e", Version: "0.1.0"},
	}})
	initMs := msSince(t0)
	rows := []row{{tool: "initialize", args: "—", result: verdict(err), code: codeOf(err, initRes), latMs: initMs, note: "handshake stdio"}}
	if err != nil {
		printTable(rows, "NO-GO en initialize")
		os.Exit(2)
	}

	// tools/list.
	t0 = time.Now()
	tl, err := mc.ListTools(ctx, mcp.ListToolsRequest{})
	listMs := msSince(t0)
	nTools := 0
	if err == nil {
		nTools = len(tl.Tools)
	}
	rows = append(rows, row{tool: "tools/list", args: "—", result: verdict(err), code: fmt.Sprint(nTools) + " tools", latMs: listMs})

	call := func(name string, args map[string]any, timeout time.Duration) (map[string]any, float64, error) {
		cctx, cancel := context.WithTimeout(ctx, timeout)
		defer cancel()
		t := time.Now()
		res, cerr := mc.CallTool(cctx, mcp.CallToolRequest{Params: mcp.CallToolParams{Name: name, Arguments: args}})
		ms := msSince(t)
		if cerr != nil {
			return nil, ms, cerr
		}
		if len(res.Content) == 0 {
			return nil, ms, fmt.Errorf("sin content")
		}
		tc, ok := res.Content[0].(mcp.TextContent)
		if !ok {
			return nil, ms, fmt.Errorf("content no-texto")
		}
		var env map[string]any
		if jerr := json.Unmarshal([]byte(tc.Text), &env); jerr != nil {
			return nil, ms, fmt.Errorf("envolvente no-JSON")
		}
		return env, ms, nil
	}

	// envelope→fila: ok/planned/error + code.
	add := func(tool, argSum string, env map[string]any, ms float64, cerr error, note string) {
		if cerr != nil {
			rows = append(rows, row{tool, argSum, "error", "TRANSPORT: " + short(cerr.Error(), 60), ms, note})
			return
		}
		ok, _ := env["ok"].(bool)
		ev, _ := env["evidence"].(map[string]any)
		code := ""
		if ev != nil {
			if c, _ := ev["code"].(string); c != "" {
				code = c
			}
			if p, _ := ev["planned"].(bool); p {
				rows = append(rows, row{tool, argSum, "planned", "planned:true", ms, note + " (sin confirm: NO ejecutada)"})
				return
			}
		}
		if ok {
			rows = append(rows, row{tool, argSum, "ok", code, ms, note})
		} else {
			if code == "" {
				code = "ok:false sin code"
			}
			rows = append(rows, row{tool, argSum, "error", code, ms, note})
		}
	}

	const T = 30 * time.Second

	// 5. Telemetría N0 (lectura, sin PII en tabla).
	for _, tc := range []struct {
		name, argSum string
		args         map[string]any
		note         string
	}{
		{"device_status", "—", nil, "hello+scopes+foreground"},
		{"get_foreground", "—", nil, ""},
		{"list_packages", "filter:\"\"", map[string]any{"filter": ""}, "conteo, sin nombres en tabla"},
		{"get_battery", "—", nil, ""},
		{"get_memory", "—", nil, "bytes"},
		{"get_storage", "basic", map[string]any{"detail": "basic"}, ""},
		{"get_cpu", "basic", map[string]any{"detail": "basic"}, ""},
		{"get_device_info", "—", nil, "sin IDs persistentes"},
		{"get_app_usage", "hours:1", map[string]any{"hours": 1}, "agregados"},
		{"get_clipboard_device", "—", nil, "solo len/hash"},
		{"media_state", "—", nil, "sesiones"},
	} {
		env, ms, cerr := call(tc.name, tc.args, T)
		add(tc.name, tc.argSum, env, ms, cerr, tc.note)
	}

	// 6. settings_get + put reversible (no-op con confirm).
	var prevVal = "30000"
	env, ms, cerr := call("settings_get", map[string]any{"namespace": "system", "key": "screen_off_timeout"}, T)
	add("settings_get", "system/screen_off_timeout", env, ms, cerr, "previo para put reversible")
	if cerr == nil {
		if ev, _ := env["evidence"].(map[string]any); ev != nil {
			if v, _ := ev["value"].(string); v != "" {
				prevVal = v
			}
		}
	}
	env, ms, cerr = call("settings_put", map[string]any{"namespace": "system", "key": "screen_off_timeout", "value": prevVal}, T)
	add("settings_put", "sin confirm", env, ms, cerr, "crítica: debe planear")
	env, ms, cerr = call("settings_put", map[string]any{"namespace": "system", "key": "screen_off_timeout", "value": prevVal, "confirm": true}, T)
	add("settings_put", "confirm:true mismo valor", env, ms, cerr, "reversible no-op; cambio neto cero")

	// 7. open_url / send_intent (VIEW libre; SEND/CALL con gate).
	env, ms, cerr = call("open_url", map[string]any{"url": "https://example.com"}, T)
	add("open_url", "VIEW https", env, ms, cerr, "apertura libre; verificar con get_foreground")
	env, ms, cerr = call("send_intent", map[string]any{"action": "VIEW", "uri": "https://example.com"}, T)
	add("send_intent", "VIEW https", env, ms, cerr, "como máximo abre editor/app")
	env, ms, cerr = call("send_intent", map[string]any{"action": "SEND", "mime": "text/plain"}, T)
	add("send_intent", "SEND sin confirm", env, ms, cerr, "crítica: debe planear")
	env, ms, cerr = call("send_intent", map[string]any{"action": "CALL", "uri": "tel:+1000000000"}, T)
	add("send_intent", "CALL sin confirm", env, ms, cerr, "crítica: debe planear")

	// 8. PIM lectura (+ críticas planeadas, no ejecutadas).
	env, ms, cerr = call("list_contacts", map[string]any{"query": "", "limit": 1, "offset": 0, "with_phone": false}, T)
	add("list_contacts", "limit:1 sin teléfono", env, ms, cerr, "conteo/hash en forense")
	env, ms, cerr = call("list_events", map[string]any{"time_min": 0, "time_max": 0}, T)
	add("list_events", "ventana 7d", env, ms, cerr, "")
	env, ms, cerr = call("list_notifications", nil, T)
	add("list_notifications", "—", env, ms, cerr, "truncadas 200ch")
	nowMs := time.Now().UnixMilli()
	env, ms, cerr = call("add_contact", map[string]any{"display_name": "E2E Probe (no ejecutar)"}, T)
	add("add_contact", "sin confirm", env, ms, cerr, "crítica: debe planear")
	env, ms, cerr = call("create_event", map[string]any{"title": "E2E Probe", "start_ms": nowMs + 3600000, "end_ms": nowMs + 7200000}, T)
	add("create_event", "sin confirm", env, ms, cerr, "crítica: debe planear")
	env, ms, cerr = call("reply_notification", map[string]any{"key": "e2e-fake-key", "text": "probe"}, T)
	add("reply_notification", "sin confirm", env, ms, cerr, "crítica: debe planear")
	env, ms, cerr = call("media_control", map[string]any{"action": "stop"}, T)
	add("media_control", "stop sin confirm", env, ms, cerr, "destructivo: debe planear")
	env, ms, cerr = call("media_control", map[string]any{"action": "pause"}, T)
	add("media_control", "pause", env, ms, cerr, "reversible")
	env, ms, cerr = call("get_location", map[string]any{"timeout_ms": 3000, "max_age_s": 300}, 20*T/10)
	add("get_location", "3s/300s", env, ms, cerr, "nunca inventa fix")

	// 9. take_photo: SOLO planned sin confirm. Ejecutada = NotRun salvo flag.
	env, ms, cerr = call("take_photo", map[string]any{"camera": "back"}, T)
	add("take_photo", "sin confirm", env, ms, cerr, "crítica SIEMPRE: debe planear")
	if *confirmPhoto {
		env, ms, cerr = call("take_photo", map[string]any{"camera": "back", "confirm": true}, 60*time.Second)
		add("take_photo", "confirm:true", env, ms, cerr, "CON CONFIRM EXPLÍCITO DEL OPERADOR")
	} else {
		rows = append(rows, row{"take_photo", "confirm:true", "NotRun", "—", 0, "sin --confirm-take-photo: NO disparada"})
	}

	// 10. UI táctica.
	env, ms, cerr = call("read_screen", nil, T)
	add("read_screen", "—", env, ms, cerr, "snapshot_id monotónico")
	var snap float64
	if cerr == nil {
		if ev, _ := env["evidence"].(map[string]any); ev != nil {
			if s, ok := ev["snapshot_id"].(float64); ok {
				snap = s
			}
		}
	}
	env, ms, cerr = call("wait_for_text", map[string]any{"text": "e2e-sonda-improbable-xyz", "timeout_ms": 1500}, 15*time.Second)
	add("wait_for_text", "sonda inexistente 1.5s", env, ms, cerr, "TIMEOUT esperado, sin mutación")
	env, ms, cerr = call("screenshot", map[string]any{"fmt": "webp", "quality": 80}, 60*time.Second)
	add("screenshot", "webp q80", env, ms, cerr, "<4MiB o PAYLOAD_TOO_LARGE")
	// Dry-run: snapshot fresco dedicado + bogus id → SELECTOR_NOT_FOUND
	// sin tocar la UI (el snapshot del read anterior puede estar rancio
	// tras wait_for_text/screenshot intermedios).
	env, ms, cerr = call("read_screen", nil, T)
	add("read_screen", "fresco pre dry-run", env, ms, cerr, "base de los dry-run")
	snap = 0
	if cerr == nil {
		if ev, _ := env["evidence"].(map[string]any); ev != nil {
			if s, ok := ev["snapshot_id"].(float64); ok {
				snap = s
			}
		}
	}
	env, ms, cerr = call("tap_node", map[string]any{"node_id": "e2e-bogus", "snapshot_id": int(snap)}, T)
	add("tap_node", "dry-run bogus", env, ms, cerr, "dry-run: NINGÚN tap real destructivo")
	env, ms, cerr = call("type_text", map[string]any{"node_id": "e2e-bogus", "snapshot_id": int(snap), "text": "probe"}, T)
	add("type_text", "dry-run bogus", env, ms, cerr, "dry-run: sin escritura real")
	env, ms, cerr = call("tap_text", map[string]any{"text": "e2e-sonda-improbable-xyz"}, T)
	add("tap_text", "sonda inexistente", env, ms, cerr, "SELECTOR_NOT_FOUND esperado")
	env, ms, cerr = call("scroll", map[string]any{"direction": "diagonal"}, T)
	add("scroll", "dirección inválida", env, ms, cerr, "VALIDATION_ERROR sin tocar UI")
	env, ms, cerr = call("scroll", map[string]any{"direction": "down"}, T)
	add("scroll", "down real", env, ms, cerr, "no destructivo; verificar con read_screen")
	env, ms, cerr = call("press_back", nil, T)
	add("press_back", "real", env, ms, cerr, "navegación reversible")
	env, ms, cerr = call("press_home", nil, T)
	add("press_home", "real", env, ms, cerr, "navegación reversible")
	env, ms, cerr = call("get_foreground", nil, T)
	add("get_foreground", "tras navegación", env, ms, cerr, "dónde quedamos")

	// 11. open_app / close_app: validación por defecto; real opt-in.
	env, ms, cerr = call("open_app", map[string]any{"package": "no-es-paquete"}, T)
	add("open_app", "forma inválida", env, ms, cerr, "VALIDATION_ERROR sin tocar UI")
	env, ms, cerr = call("close_app", map[string]any{"package": "no-es-paquete"}, T)
	add("close_app", "forma inválida", env, ms, cerr, "VALIDATION_ERROR sin tocar UI")
	if *realOpenApp {
		env, ms, cerr = call("open_app", map[string]any{"package": "com.android.settings"}, 60*time.Second)
		add("open_app", "settings real", env, ms, cerr, "CON --real-open-app; verify foreground")
	} else {
		rows = append(rows, row{"open_app", "settings real", "NotRun", "—", 0, "sin --real-open-app: dry-run documentado"})
		rows = append(rows, row{"close_app", "settings real", "NotRun", "—", 0, "force-stop real omitido (disruptivo)"})
	}

	// 12. resources + prompts.
	t0 = time.Now()
	rl, rerr := mc.ListResources(ctx, mcp.ListResourcesRequest{})
	rMs := msSince(t0)
	nRes := 0
	if rerr == nil {
		nRes = len(rl.Resources)
	}
	rows = append(rows, row{"resources/list", "—", verdict(rerr), fmt.Sprint(nRes) + " resources", rMs, ""})
	if rerr == nil {
		for _, r := range rl.Resources {
			t0 = time.Now()
			_, rerr := mc.ReadResource(ctx, mcp.ReadResourceRequest{Params: mcp.ReadResourceParams{URI: r.URI}})
			rows = append(rows, row{"resources/read", short(r.URI, 40), verdict(rerr), codeOf(rerr, nil), msSince(t0), "decorativo, sin node_ids"})
		}
	}
	t0 = time.Now()
	pl, perr := mc.ListPrompts(ctx, mcp.ListPromptsRequest{})
	pMs := msSince(t0)
	nPr := 0
	if perr == nil {
		nPr = len(pl.Prompts)
	}
	rows = append(rows, row{"prompts/list", "—", verdict(perr), fmt.Sprint(nPr) + " prompts", pMs, ""})
	if perr == nil {
		for _, p := range pl.Prompts {
			t0 = time.Now()
			_, gerr := mc.GetPrompt(ctx, mcp.GetPromptRequest{Params: mcp.GetPromptParams{Name: p.Name, Arguments: map[string]string{}}})
			rows = append(rows, row{"prompts/get", p.Name, verdict(gerr), codeOf(gerr, nil), msSince(t0), "guía, no toca dispositivo"})
		}
	}

	printTable(rows, "")
}

func msSince(t time.Time) float64 { return float64(time.Since(t).Microseconds()) / 1000.0 }

func verdict(err error) string {
	if err != nil {
		return "error"
	}
	return "ok"
}

func codeOf(err error, _ any) string {
	if err != nil {
		return "TRANSPORT: " + short(err.Error(), 60)
	}
	return ""
}

func short(s string, n int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) > n {
		return s[:n] + "…"
	}
	return s
}

func printTable(rows []row, banner string) {
	var b strings.Builder
	b.WriteString("# jav-e2e — " + time.Now().UTC().Format("2006-01-02 15:04:05Z") + "\n\n")
	if banner != "" {
		b.WriteString("**" + banner + "**\n\n")
	}
	b.WriteString("| herramienta | args | resultado | code | latencia_ms |\n")
	b.WriteString("|---|---|---|---|---|\n")
	var nOK, nPlanned, nErr, nSkip int
	var latSum, latMax float64
	for _, r := range rows {
		b.WriteString(fmt.Sprintf("| %s | %s | %s | %s | %.0f |\n", r.tool, r.args, r.result, short(r.code, 48), r.latMs))
		switch r.result {
		case "ok":
			nOK++
		case "planned", "dry-run":
			nPlanned++
		case "NotRun":
			nSkip++
		default:
			nErr++
		}
		latSum += r.latMs
		if r.latMs > latMax {
			latMax = r.latMs
		}
	}
	b.WriteString(fmt.Sprintf("\nResumen: ok=%d planned/dry-run=%d error=%d NotRun=%d lat_media=%.0fms lat_max=%.0fms\n",
		nOK, nPlanned, nErr, nSkip, latSum/max(1, float64(len(rows))), latMax))
	b.WriteString("\nNotas: take_photo confirm:true = NotRun sin --confirm-take-photo; " +
		"tap_node/type_text = dry-run bogus (SELECTOR_NOT_FOUND o STALE_SNAPSHOT; " +
		"en ambos sin mutación: el snapshot se valida antes de actuar); " +
		"settings_put confirm:true = no-op mismo valor (cambio neto cero); " +
		"críticas Jam (add/create/reply/media-stop/photo/settings) sin confirm = planned sin ejecutar; " +
		"send_intent SEND/CALL sin confirm → ok del servidor (gate en Jam, ver informe).\n")
	fmt.Print(b.String())
	if _, err := os.Stat("logs"); err == nil {
		name := "logs/jav-e2e-" + time.Now().UTC().Format("20060102-150405") + ".md"
		_ = os.WriteFile(name, []byte(b.String()), 0o600)
		fmt.Fprintf(os.Stderr, "jav-e2e: tabla guardada en %s\n", name)
	}
	_ = filepath.Separator
}

func max(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}
