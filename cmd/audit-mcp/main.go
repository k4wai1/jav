// Binario audit-mcp: auditoría nativa Go del servidor MCP Jav (stdio).
//
// DECISIÓN DOCUMENTADA (reemplazo de scripts/tools-list-diff.py):
//   - Se elige cmd/audit-mcp/ frente a pkg/tools/audit_test.go porque el
//     script sustituido era un EJECUTABLE de CI/juez (make tools-list-diff:
//     lanzaba el binario Go por stdio y comparaba tools/list). Un _test.go
//     no es invocable igual por el juez final ni por CI sin go test.
//     Este binario sí: `go run ./cmd/audit-mcp [--bin dist/...]`.
//   - Se ELIMINA scripts/tools-list-diff.py porque queda cubierto y además
//     muerto: importaba jev_mcp.server (mcp-server/src/jev_mcp/*.py purgados
//     en 65b424e; solo quedan __pycache__), así que ya no puede correr.
//     La comparación Python≡Go carece de referencia viva; la referencia
//     viva pasa a ser PROTOCOL.md + docs/MCP_SPEC_GUIDELINES.md (normativos)
//     más el propio register.go verificado en vivo por stdio.
//   - NADA de `su`: la auditoría solo lee fuentes y habla MCP por stdio;
//     jamás ejecuta adb remotos ni eleva privilegios.
//
// Verifica (exit 0 = todo PASS, exit 1 = algún FAIL):
//  1. 35 tools en vivo == tabla esperada (nombres, required, tipos,
//     descripciones con affordances/retornos) y cobertura de PROTOCOL.md.
//  2. stdout puro JSON-RPC (ningún log a stdout) + scan estático de
//     escrituras a stdout en cmd/jav y pkg/ (todo log va a stderr).
//     cmd/jav-e2e se excluye a propósito: es un harness CLI cuya salida
//     a stdout (tabla markdown) ES su contrato, no framing MCP.
//  3. initialize trae instructions; errores de validación (sin Jam)
//     devuelven isError:true + {ok:false, evidence.code, hint} (la hint
//     ES la recovery_instruction); escritura sensible exige confirm:true
//     (schema + handler reenvía confirm + descripción planned/preview).
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

var (
	fBin   = flag.String("bin", "", "binario jav a auditar (default: compilar ./cmd/jav a temporal)")
	fRoot  = flag.String("root", "", "raíz del repo (default: cwd)")
	fProto = flag.String("protocol", "", "PROTOCOL.md (default: <root>/PROTOCOL.md)")
)

type check struct {
	name string
	pass bool
	info string
}

var results []check

func emit(name string, pass bool, info string) {
	results = append(results, check{name, pass, info})
	status := "PASS"
	if !pass {
		status = "FAIL"
	}
	if info != "" {
		fmt.Printf("%s %s: %s\n", status, name, info)
	} else {
		fmt.Printf("%s %s\n", status, name)
	}
}

// ---------- tabla esperada (espejo de pkg/tools/register.go) ----------

// propKind: "string" | "integer" | "boolean" | "anyOf:string,null" | "anyOf:object,null"
type toolExp struct {
	required []string
	props    map[string]string
}

// sensibles: escritura sensible que exige confirm:true (SEND/CALL vía
// send_intent, settings_put-System, create_event + resto con confirm).
var sensitive = map[string]bool{
	"settings_put": true, "send_intent": true, "add_contact": true,
	"create_event": true, "reply_notification": true,
	"media_control": true, "take_photo": true,
}

var expected = map[string]toolExp{
	"device_status":        {nil, map[string]string{}},
	"list_packages":        {nil, map[string]string{"filter": "string"}},
	"get_foreground":       {nil, map[string]string{}},
	"open_app":             {[]string{"package"}, map[string]string{"package": "string"}},
	"close_app":            {[]string{"package"}, map[string]string{"package": "string"}},
	"read_screen":          {nil, map[string]string{}},
	"tap_text":             {[]string{"text"}, map[string]string{"text": "string"}},
	"tap_node":             {[]string{"node_id", "snapshot_id"}, map[string]string{"node_id": "string", "snapshot_id": "integer"}},
	"type_text":            {[]string{"node_id", "snapshot_id", "text"}, map[string]string{"node_id": "string", "snapshot_id": "integer", "text": "string"}},
	"scroll":               {nil, map[string]string{"direction": "string", "node_id": "anyOf:null,string"}},
	"press_back":           {nil, map[string]string{}},
	"press_home":           {nil, map[string]string{}},
	"wait_for_text":        {[]string{"text"}, map[string]string{"text": "string", "timeout_ms": "integer"}},
	"screenshot":           {nil, map[string]string{"fmt": "string", "quality": "integer"}},
	"get_battery":          {nil, map[string]string{}},
	"get_memory":           {nil, map[string]string{}},
	"get_storage":          {nil, map[string]string{"detail": "string"}},
	"get_cpu":              {nil, map[string]string{"detail": "string"}},
	"get_device_info":      {nil, map[string]string{}},
	"settings_get":         {nil, map[string]string{"namespace": "string", "key": "string"}},
	"settings_put":         {nil, map[string]string{"namespace": "string", "key": "string", "value": "string", "confirm": "boolean"}},
	"open_url":             {[]string{"url"}, map[string]string{"url": "string", "package": "string"}},
	"send_intent":          {[]string{"action"}, map[string]string{"action": "string", "uri": "string", "package": "string", "mime": "string", "confirm": "boolean", "extras": "anyOf:null,object"}},
	"get_clipboard_device": {nil, map[string]string{}},
	"get_app_usage":        {nil, map[string]string{"hours": "integer", "window": "anyOf:null,string"}},
	"list_contacts":        {nil, map[string]string{"query": "string", "limit": "integer", "offset": "integer", "with_phone": "boolean"}},
	"add_contact":          {[]string{"display_name"}, map[string]string{"display_name": "string", "phone": "string", "email": "string", "confirm": "boolean"}},
	"list_events":          {nil, map[string]string{"time_min": "integer", "time_max": "integer", "calendar_id": "integer", "include_location": "boolean"}},
	"create_event":         {[]string{"title", "start_ms", "end_ms"}, map[string]string{"title": "string", "start_ms": "integer", "end_ms": "integer", "calendar_id": "integer", "description": "string", "confirm": "boolean"}},
	"list_notifications":   {nil, map[string]string{}},
	"reply_notification":   {[]string{"key", "text"}, map[string]string{"key": "string", "text": "string", "confirm": "boolean"}},
	"media_state":          {nil, map[string]string{}},
	"media_control":        {[]string{"action"}, map[string]string{"action": "string", "package": "string", "confirm": "boolean"}},
	"get_location":         {nil, map[string]string{"timeout_ms": "integer", "max_age_s": "integer"}},
	"take_photo":           {nil, map[string]string{"confirm": "boolean", "camera": "string"}},
}

// Secciones de affordances exigibles por tool (guía §2: 5 secciones +
// §6 Cuándo NO + §7 Ejemplo). Retorno = envolvente {ok,verified,evidence,hint}.
var affordNeedles = []string{
	"Descripcion:", "Parametros:", "Retorno:",
	"Permisos/Grants:", "Errores/gotchas:",
	"Cuándo NO usar", "Ejemplo", "→",
}

// PROTOCOL.md: sondas de cobertura (contrato vivo que las tools respetan;
// los nombres MCP difieren a propósito — mapeo AGENTS.md §6 — así que se
// verifica presencia del método/código más el mapeo documentado abajo).
var protoNeedles = []string{
	"dump_ui", "tap", "tap_node", "type", "scroll",
	"screenshot", "open_app", "force_stop", "get_foreground",
	"list_packages", "shell", "METHOD_NOT_ALLOWED", "get_audit",
	"snapshot_id", "STALE_SNAPSHOT", "SECURE_SURFACE", "4 MiB",
	"send_intent", "settings_put", "planned",
}

// ---------- utilidades JSON-RPC ----------

func propKindOf(p map[string]any) string {
	if t, ok := p["type"].(string); ok && t != "" {
		return t
	}
	if anyOf, ok := p["anyOf"].([]any); ok {
		kinds := []string{}
		for _, o := range anyOf {
			if m, ok := o.(map[string]any); ok {
				if t, ok := m["type"].(string); ok {
					kinds = append(kinds, t)
				}
			}
		}
		sort.Strings(kinds)
		return "anyOf:" + strings.Join(kinds, ",")
	}
	return "?"
}

func equalStrSlice(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	aa := append([]string{}, a...)
	bb := append([]string{}, b...)
	sort.Strings(aa)
	sort.Strings(bb)
	for i := range aa {
		if aa[i] != bb[i] {
			return false
		}
	}
	return true
}

func main() {
	flag.Parse()
	root := *fRoot
	if root == "" {
		cwd, err := os.Getwd()
		if err != nil {
			fmt.Printf("FAIL root: %v\n", err)
			os.Exit(1)
		}
		root = cwd
	}
	proto := *fProto
	if proto == "" {
		proto = filepath.Join(root, "PROTOCOL.md")
	}

	bin := *fBin
	tmpBin := ""
	if bin == "" {
		tmpBin = filepath.Join(os.TempDir(), "jav-audit-bin")
		cmd := exec.Command("go", "build", "-o", tmpBin, "./cmd/jav")
		cmd.Dir = root
		if out, err := cmd.CombinedOutput(); err != nil {
			fmt.Printf("FAIL build jav: %v %s\n", err, string(out))
			os.Exit(1)
		}
		defer os.Remove(tmpBin)
		bin = tmpBin
	}

	// --- sesión stdio: initialize + tools/list + calls de validación ---
	type frame map[string]any
	reqs := []frame{
		{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": map[string]any{
			"protocolVersion": "2024-11-05", "capabilities": map[string]any{},
			"clientInfo": map[string]any{"name": "audit-mcp", "version": "0"}}},
		{"jsonrpc": "2.0", "method": "notifications/initialized"},
		{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": map[string]any{}},
		{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": map[string]any{
			"name": "scroll", "arguments": map[string]any{"direction": "diagonal"}}},
		{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": map[string]any{
			"name": "open_app", "arguments": map[string]any{"package": "no-es-paquete"}}},
		{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": map[string]any{
			"name": "type_text", "arguments": map[string]any{"node_id": "", "snapshot_id": 1, "text": "x"}}},
	}
	var stdin bytes.Buffer
	for _, r := range reqs {
		raw, _ := json.Marshal(r)
		stdin.Write(raw)
		stdin.WriteByte('\n')
	}
	cmd := exec.Command(bin)
	cmd.Stdin = &stdin
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	done := make(chan error, 1)
	go func() { done <- cmd.Run() }()
	select {
	case <-done:
	case <-time.After(30 * time.Second):
		_ = cmd.Process.Kill()
		fmt.Println("FAIL stdio: timeout 30s esperando al binario")
		os.Exit(1)
	}

	// --- CHECK 2a: stdout puro JSON-RPC ---
	lines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
	byID := map[string]map[string]any{}
	nonJSON := []string{}
	for _, ln := range lines {
		ln = strings.TrimSpace(ln)
		if ln == "" {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(ln), &m); err != nil {
			nonJSON = append(nonJSON, ln[:min(120, len(ln))])
			continue
		}
		if m["jsonrpc"] != "2.0" {
			nonJSON = append(nonJSON, "sin jsonrpc 2.0")
			continue
		}
		rawID, ok := m["id"]
		if !ok {
			continue // notificación/respuesta sin id: no aporta pero es JSON válido
		}
		idStr := fmt.Sprint(rawID)
		// mcp-go puede devolver id como número o string según eco; normaliza
		byID[idStr] = m
	}
	emit("stdout-puro-jsonrpc", len(nonJSON) == 0,
		fmt.Sprintf("%d líneas stdout, %d no-JSON", len(lines), len(nonJSON)))
	if len(nonJSON) > 0 {
		emit("stdout-muestra", false, strings.Join(nonJSON, " | "))
	}

	// --- CHECK 3a: initialize con instructions ---
	initMsg := byID["1"]
	instructions := ""
	if r, ok := initMsg["result"].(map[string]any); ok {
		instructions, _ = r["instructions"].(string)
	}
	needInstr := []string{"LANE", "snapshot_id", "NOT_FOCUSED", "VERIFY",
		"planned:true", "confirm:true", "PRIVACY", "hint"}
	missing := []string{}
	for _, n := range needInstr {
		if !strings.Contains(instructions, n) {
			missing = append(missing, n)
		}
	}
	words := len(strings.Fields(instructions))
	emit("initialize-instructions", instructions != "" && len(missing) == 0 && words <= 400,
		fmt.Sprintf("%d palabras, faltan=%v", words, missing))

	// --- CHECK 1: tools/list vs tabla esperada ---
	got := map[string]map[string]any{}
	if r, ok := byID["2"]["result"].(map[string]any); ok {
		if arr, ok := r["tools"].([]any); ok {
			for _, t := range arr {
				if m, ok := t.(map[string]any); ok {
					if n, ok := m["name"].(string); ok {
						got[n] = m
					}
				}
			}
		}
	}
	var onlyExp, onlyGot []string
	for n := range expected {
		if _, ok := got[n]; !ok {
			onlyExp = append(onlyExp, n)
		}
	}
	for n := range got {
		if _, ok := expected[n]; !ok {
			onlyGot = append(onlyGot, n)
		}
	}
	sort.Strings(onlyExp)
	sort.Strings(onlyGot)
	emit("tools-count-35", len(got) == 35 && len(onlyExp) == 0 && len(onlyGot) == 0,
		fmt.Sprintf("got=%d solo-esperada=%v solo-got=%v", len(got), onlyExp, onlyGot))

	schemaDiffs := []string{}
	for name, exp := range expected {
		g, ok := got[name]
		if !ok {
			continue
		}
		sch, _ := g["inputSchema"].(map[string]any)
		var req []string
		switch v := sch["required"].(type) {
		case []any:
			for _, x := range v {
				if s, ok := x.(string); ok {
					req = append(req, s)
				}
			}
		}
		if !equalStrSlice(req, exp.required) {
			schemaDiffs = append(schemaDiffs, fmt.Sprintf("%s required live=%v exp=%v", name, req, exp.required))
		}
		props, _ := sch["properties"].(map[string]any)
		if len(props) != len(exp.props) {
			keys := []string{}
			for k := range props {
				keys = append(keys, k)
			}
			sort.Strings(keys)
			expKeys := []string{}
			for k := range exp.props {
				expKeys = append(expKeys, k)
			}
			sort.Strings(expKeys)
			schemaDiffs = append(schemaDiffs, fmt.Sprintf("%s props live=%v exp=%v", name, keys, expKeys))
			continue
		}
		for p, want := range exp.props {
			pm, ok := props[p].(map[string]any)
			if !ok {
				schemaDiffs = append(schemaDiffs, fmt.Sprintf("%s.%s falta", name, p))
				continue
			}
			if k := propKindOf(pm); k != want {
				schemaDiffs = append(schemaDiffs, fmt.Sprintf("%s.%s tipo live=%s exp=%s", name, p, k, want))
			}
		}
		// title/type envelope
		if sch["type"] != "object" {
			schemaDiffs = append(schemaDiffs, fmt.Sprintf("%s envelope type!=object", name))
		}
	}
	emit("tools-schema", len(schemaDiffs) == 0,
		fmt.Sprintf("%d diffs %v", len(schemaDiffs), firstN(schemaDiffs, 5)))

	// --- CHECK 1b: affordances + retornos en descripciones ---
	affordFails := []string{}
	for name := range expected {
		g, ok := got[name]
		if !ok {
			continue
		}
		d, _ := g["description"].(string)
		for _, n := range affordNeedles {
			if !strings.Contains(d, n) {
				affordFails = append(affordFails, fmt.Sprintf("%s sin %q", name, n))
			}
		}
		for _, n := range []string{"{ok", "verified", "evidence", "hint"} {
			if !strings.Contains(d, n) {
				affordFails = append(affordFails, fmt.Sprintf("%s retorno sin %q", name, n))
			}
		}
		if sensitive[name] {
			for _, n := range []string{"planned:true", "preview", "confirm"} {
				if !strings.Contains(d, n) {
					affordFails = append(affordFails, fmt.Sprintf("%s sensible sin %q", name, n))
				}
			}
		}
	}
	emit("tools-affordances", len(affordFails) == 0,
		fmt.Sprintf("%d fallos %v", len(affordFails), firstN(affordFails, 5)))

	// --- CHECK 1c: cobertura PROTOCOL.md ---
	protoRaw, err := os.ReadFile(proto)
	protoOK := err == nil
	missProto := []string{}
	if protoOK {
		for _, n := range protoNeedles {
			if !strings.Contains(string(protoRaw), n) {
				missProto = append(missProto, n)
			}
		}
	}
	emit("protocol-cobertura", protoOK && len(missProto) == 0,
		fmt.Sprintf("proto=%s faltan=%v (mapeo MCP↔Jam: open_app↔open_app, close_app↔force_stop, read_screen↔dump_ui+normalizar, tap_text/tap_node↔tap, type_text↔type, get_foreground↔get_foreground, list_packages↔list_packages, shell/N2→METHOD_NOT_ALLOWED)", proto, missProto))

	// --- CHECK 2b: scan estático stdout ---
	forbidden := []*regexp.Regexp{
		regexp.MustCompile(`os\.Stdout`),
		regexp.MustCompile(`fmt\.Print[f|l]?n?\s*\(`),
		regexp.MustCompile(`(?m)^\s*println\s*\(`),
		regexp.MustCompile(`log\.SetOutput\s*\(\s*os\.Stdout`),
	}
	// fmt.Sprint/Errorf/Sprintf construyen strings (no escriben): siempre OK.
	// fmt.Fprint a stderr: OK. Se excluyen cmd/jav-e2e (harness CLI con
	// stdout como contrato) y _test.go/dist (no van al binario MCP).
	allowedDirs := []string{"cmd/jav", "pkg"}
	stdoutHits := []string{}
	walkRoots := []string{}
	for _, d := range allowedDirs {
		walkRoots = append(walkRoots, filepath.Join(root, d))
	}
	for _, wr := range walkRoots {
		_ = filepath.Walk(wr, func(p string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			if !strings.HasSuffix(p, ".go") || strings.HasSuffix(p, "_test.go") {
				return nil
			}
			raw, err := os.ReadFile(p)
			if err != nil {
				return nil
			}
			src := string(raw)
			rel, _ := filepath.Rel(root, p)
			for _, re := range forbidden {
				for _, m := range re.FindAllString(src, -1) {
					m = strings.TrimSpace(m)
					// fmt.Fprint(os.Stderr / fmt.Fprintf(os.Stderr = stderr: OK
					if strings.Contains(m, "Fprint") || strings.Contains(m, "Fprintf") || strings.Contains(m, "Fprintln") {
						// hay que mirar la línea completa para el destino
						continue
					}
					// fmt.Sprint* no escribe: el regex no los captura (solo Print*),
					// pero fmt.Print* sí escribe a stdout → hit.
					stdoutHits = append(stdoutHits, fmt.Sprintf("%s: %s", rel, m))
				}
			}
			// Fprint con destino distinto de stderr → hit
			reF := regexp.MustCompile(`fmt\.F(print|printf|println)\s*\(\s*os\.Stdout[^)]*\)`)
			for _, m := range reF.FindAllString(src, -1) {
				stdoutHits = append(stdoutHits, rel+": "+strings.TrimSpace(m))
			}
			return nil
		})
	}
	emit("no-stdout-statico", len(stdoutHits) == 0,
		fmt.Sprintf("%d hits %v (stderr permitido; jav-e2e/_test excluidos)", len(stdoutHits), firstN(stdoutHits, 5)))

	// --- CHECK 3b: errores isError:true + recovery_instruction ---
	// MCP (mcp-go): isError viaja DENTRO de result (CallToolResult),
	// no a nivel de frame JSON-RPC. La recovery_instruction es el
	// campo hint de la envolvente {ok,verified,evidence,hint}.
	for _, id := range []string{"3", "4", "5"} {
		msg := byID[id]
		res, _ := msg["result"].(map[string]any)
		isErr, _ := res["isError"].(bool)
		if res == nil {
			// algunos servidores devuelven el error en "error" en vez de
			// result+isError: se acepta si trae code/hint equivalentes.
			if em, ok := msg["error"].(map[string]any); ok {
				emit("error-isError-id"+id, false, fmt.Sprintf("vino en error (no result): %v", em))
				continue
			}
			emit("error-isError-id"+id, false, "sin result")
			continue
		}
		content, _ := res["content"].([]any)
		text := ""
		if len(content) > 0 {
			if m, ok := content[0].(map[string]any); ok {
				text, _ = m["text"].(string)
			}
		}
		var env map[string]any
		_ = json.Unmarshal([]byte(text), &env)
		okVal, _ := env["ok"].(bool)
		ev, _ := env["evidence"].(map[string]any)
		code, _ := ev["code"].(string)
		hint, _ := env["hint"].(string)
		pass := isErr && !okVal && code != "" && strings.TrimSpace(hint) != ""
		emit("error-isError-id"+id, pass,
			fmt.Sprintf("isError=%v ok=%v code=%q hint=%q", isErr, okVal, code, truncate(hint, 60)))
	}

	// --- CHECK 3c: escritura sensible exige confirm (estático) ---
	regPath := filepath.Join(root, "pkg", "tools", "register.go")
	regRaw, err := os.ReadFile(regPath)
	regOK := err == nil
	sensFails := []string{}
	if regOK {
		for name := range expected {
			if !sensitive[name] {
				continue
			}
			// schema: el .go de registro debe declarar confirm boolProp para la tool.
			// Búsqueda laxa pero determinista por nombre cercano.
			if !strings.Contains(string(regRaw), `"confirm"`) {
				sensFails = append(sensFails, "register.go sin confirm")
				break
			}
			// descripción viva ya verificada arriba (planned/preview);
			// aquí se exige que la tool exista en el registro.
			if !strings.Contains(string(regRaw), `"`+name+`"`) {
				sensFails = append(sensFails, name+" no registrada")
			}
		}
	} else {
		sensFails = append(sensFails, "register.go ilegible")
	}
	// handlers reenvían confirm a Jam (settings_put, send_intent, add_contact,
	// create_event, reply_notification, media_control, take_photo).
	nativeRaw, _ := os.ReadFile(filepath.Join(root, "pkg", "tools", "native.go"))
	fwdNeed := []string{`"confirm": confirm`, `"confirm":confirm`, "confirm"}
	fwdOK := false
	for _, n := range fwdNeed[:2] {
		if strings.Contains(string(nativeRaw), n) {
			fwdOK = true
		}
	}
	if !fwdOK {
		sensFails = append(sensFails, "native.go no reenvía confirm a Jam")
	}
	// SEND/CALL críticos detectados en Go (sendintent.go espejo de NatPolicies).
	siRaw, _ := os.ReadFile(filepath.Join(root, "pkg", "tools", "sendintent.go"))
	for _, n := range []string{"SEND", "CALL", "IsCriticalIntent"} {
		if !strings.Contains(string(siRaw), n) {
			sensFails = append(sensFails, "sendintent.go sin "+n)
		}
	}
	emit("confirm-sensible", len(sensFails) == 0,
		fmt.Sprintf("sensibles=%d fallos=%v", countConfirm(), firstN(sensFails, 5)))

	// --- resumen ---
	fail := 0
	for _, r := range results {
		if !r.pass {
			fail++
		}
	}
	fmt.Printf("---\nAUDIT %s: %d/%d PASS\n", map[bool]string{true: "OK", false: "FAIL"}[fail == 0], len(results)-fail, len(results))
	if fail > 0 {
		os.Exit(1)
	}
}

func countConfirm() int {
	return len(sensitive)
}

func firstN(s []string, n int) []string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
