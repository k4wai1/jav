package tools

import (
	"context"
	"encoding/json"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/normalizer"
)

// Helpers de args, validación, envolvente y Jam (equiv. tools/_base.py
// más validación client-side de enums/rangos/formas, spec §6.3).

// Handler es un handler MCP de tool.
type Handler = server.ToolHandlerFunc

var packageRe = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$`)

func argsOf(req mcp.CallToolRequest) map[string]any {
	args := req.GetArguments()
	if args == nil {
		return map[string]any{}
	}
	return args
}

func getString(args map[string]any, key, def string) string {
	if v, ok := args[key].(string); ok {
		return v
	}
	return def
}

func getBool(args map[string]any, key string, def bool) bool {
	if v, ok := args[key].(bool); ok {
		return v
	}
	return def
}

func getInt(args map[string]any, key string, def int) int {
	switch v := args[key].(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	}
	return def
}

func getInt64(args map[string]any, key string, def int64) int64 {
	switch v := args[key].(type) {
	case int:
		return int64(v)
	case int64:
		return v
	case float64:
		return int64(v)
	}
	return def
}

func getNullableString(args map[string]any, key string) string {
	if v, ok := args[key].(string); ok {
		return v
	}
	return ""
}

func hasKey(args map[string]any, key string) bool {
	_, ok := args[key]
	return ok
}

// result serializa la envolvente como único TextContent JSON; isError = !ok.
func result(env jam.Envelope) (*mcp.CallToolResult, error) {
	raw, err := json.Marshal(env)
	if err != nil {
		r := mcp.NewToolResultText(`{"ok":false,"verified":false,"evidence":{"code":"ENCODING_ERROR","error":"marshal"},"hint":""}`)
		r.IsError = true
		return r, nil
	}
	r := mcp.NewToolResultText(string(raw))
	if ok, _ := env["ok"].(bool); !ok {
		r.IsError = true
	}
	return r, nil
}

func validationError(msg string) jam.Envelope {
	return jam.Fail("VALIDATION_ERROR", msg, "revisa los parametros de la tool")
}

// --- Validaciones client-side (spec §6.3) ---

func checkPackage(pkg string) *jam.Envelope {
	if !packageRe.MatchString(pkg) {
		e := validationError("package con forma inválida: " + pkg)
		return &e
	}
	return nil
}

func checkDirection(d string) *jam.Envelope {
	switch d {
	case "up", "down", "left", "right":
		return nil
	}
	e := validationError("direction inválida (up|down|left|right): " + d)
	return &e
}

func checkFmt(f string) *jam.Envelope {
	if f == "png" || f == "webp" {
		return nil
	}
	e := validationError("fmt inválido (png|webp): " + f)
	return &e
}

func checkDetail(d string) *jam.Envelope {
	if d == "basic" || d == "fine" {
		return nil
	}
	e := validationError("detail inválido (basic|fine): " + d)
	return &e
}

func checkMediaAction(a string) *jam.Envelope {
	switch a {
	case "play", "pause", "next", "prev", "stop":
		return nil
	}
	e := validationError("action inválida (play|pause|next|prev|stop): " + a)
	return &e
}

func checkCamera(c string) *jam.Envelope {
	if c == "back" || c == "front" {
		return nil
	}
	e := validationError("camera inválida (back|front): " + c)
	return &e
}

func checkURL(u string) *jam.Envelope {
	if strings.Contains(u, "://") {
		return nil
	}
	e := validationError("url sin esquema ://: " + u)
	return &e
}

func checkNamespace(ns string) *jam.Envelope {
	switch ns {
	case "system", "secure", "global":
		return nil
	}
	e := validationError("namespace inválido (system|secure|global): " + ns)
	return &e
}

func checkWindow(w string) *jam.Envelope {
	switch w {
	case "", "today", "week", "raw":
		return nil
	}
	e := validationError("window inválida (today|week|raw): " + w)
	return &e
}

// --- Llamadas Jam con latencia ---

// jamCall abre conexión, ejecuta y cierra (dial + hello + método + close).
func jamCall(fn func(c *jam.Client) (map[string]any, *jam.JamError)) jam.Envelope {
	t0 := time.Now()
	c, jerr := jam.Dial()
	if jerr != nil {
		return jam.JamFail(jerr)
	}
	defer c.Close()
	res, jerr := fn(c)
	if jerr != nil {
		return jam.JamFail(jerr)
	}
	_ = t0
	return jam.OK(true, res, "")
}

// jamCallLatency igual + latency_ms en evidence (carril native).
func jamCallLatency(method string, params map[string]any) jam.Envelope {
	t0 := time.Now()
	ms := func() float64 { return float64(time.Since(t0).Microseconds()) / 1000.0 }
	c, jerr := jam.Dial()
	if jerr != nil {
		d := jam.JamFail(jerr)
		d["evidence"].(map[string]any)["latency_ms"] = ms()
		return d
	}
	defer c.Close()
	res, jerr := c.Call(method, params)
	if jerr != nil {
		d := jam.JamFail(jerr)
		d["evidence"].(map[string]any)["latency_ms"] = ms()
		return d
	}
	ev := map[string]any{}
	for k, v := range res {
		ev[k] = v
	}
	ev["latency_ms"] = ms()
	verified := true
	if p, _ := ev["planned"].(bool); p {
		verified = false
	}
	return jam.OK(verified, ev, "")
}

// --- Dimensiones de pantalla (cache `adb shell wm size`) ---

var (
	screenMu     sync.Mutex
	screenW      int
	screenH      int
	screenLoaded bool
)

func refreshScreenSize() {
	out, err := exec.Command("adb", "shell", "wm", "size").Output()
	if err != nil {
		return
	}
	m := regexp.MustCompile(`(\d+)x(\d+)`).FindSubmatch(out)
	if len(m) == 3 {
		w := atoi(string(m[1]))
		h := atoi(string(m[2]))
		if w > 0 && h > 0 {
			screenW, screenH = w, h
		}
	}
}

func atoi(s string) int {
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0
		}
		n = n*10 + int(c-'0')
	}
	return n
}

func nowMs() int64 { return time.Now().UnixMilli() }

// ScreenWidth ancho en px (cacheado). 0 si no se puede.
func ScreenWidth() int {
	screenMu.Lock()
	defer screenMu.Unlock()
	if !screenLoaded {
		refreshScreenSize()
		screenLoaded = true
	}
	return screenW
}

// ScreenHeight altura en px (cacheada). 0 si no se puede.
func ScreenHeight() int {
	screenMu.Lock()
	defer screenMu.Unlock()
	if !screenLoaded {
		refreshScreenSize()
		screenLoaded = true
	}
	return screenH
}

// readScreenState dump + normalizer + tabla (compartido por handler).
func readScreenState() jam.Envelope {
	c, jerr := jam.Dial()
	if jerr != nil {
		return jam.JamFail(jerr)
	}
	defer c.Close()
	dump, jerr := c.DumpUI()
	if jerr != nil {
		return jam.JamFail(jerr)
	}
	st := normalizer.Normalize(dump, normalizer.MaxCandidates, ScreenHeight(), ScreenWidth())
	cands := make([]map[string]any, 0, len(st.Candidates))
	for _, cd := range st.Candidates {
		cands = append(cands, map[string]any{
			"id": cd.ID, "label": cd.Compact(), "cls": cd.Cls,
			"class_short": cd.ClassShort(), "flags": cd.Flags(),
			"clickable": cd.Clickable, "editable": cd.Editable,
			"focused": cd.Focused, "scrollable": cd.Scrollable,
			"visible": cd.Visible, "text": cd.Text, "desc": cd.Desc,
			"resource_id": cd.ResourceID,
			"bounds":      []int{cd.Bounds[0], cd.Bounds[1], cd.Bounds[2], cd.Bounds[3]},
		})
	}
	rows, _ := normalizer.BuildTable(st.Candidates, ScreenWidth(), ScreenHeight())
	var first any
	if fr, ok := normalizer.FirstResult(rows); ok {
		first = fr
	}
	return jam.OK(true, map[string]any{
		"package": st.Package, "activity": st.Activity,
		"snapshot_id": st.SnapshotID, "raw_count": st.RawCount,
		"screen_height": ScreenHeight(), "screen_width": ScreenWidth(),
		"focused_field": st.Focused.AsView(),
		"first_result":  first,
		"candidates":    cands,
		"render":        normalizer.FormatState(st),
	}, "")
}

var _ = context.Background
