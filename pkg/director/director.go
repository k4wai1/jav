package director

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math"
	"os/exec"
	"regexp"
	"strings"
	"time"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/jev"
	"github.com/k4wai1/jav/pkg/normalizer"
)

// Adaptadores pasivos de ejecución paso a paso + resolve_element táctico
// (Jev vía OPENROUTER_API_KEY/JEV_MODEL). Sin bucles, sin planificación
// macro, sin clientes que decidan pasos: OpenCode/cliente externo ES el
// único Sistema 2. El slug S2 por OpenRouter (p.ej. deepseek/deepseek-chat)
// lo configura el director externo; aquí no vive ningún provider S2.
// El director externo invoca resolve_element con (screen_goal, tabla
// serializada, snapshot_id) y ejecuta una primitiva por paso.

// --- Resolver ciego (UMA Choice) ---

// BuildResolveState construye (state, questions) ciegos al goal global.
func BuildResolveState(screenGoal string, serial []jev.SerialRow, snapshotID int64, currentApp string, firstResult any) (map[string]any, map[string]map[string]any) {
	targetKeys := make([]string, 0, len(serial)+1)
	for _, r := range serial {
		if len(r) > 0 {
			targetKeys = append(targetKeys, fmt.Sprint(r[0]))
		}
	}
	targetKeys = append(targetKeys, "NONE")
	crit := map[string]any{}
	for _, k := range targetKeys {
		crit[k] = k
	}
	state := map[string]any{
		"screen_goal": screenGoal, "current_app": currentApp,
		"snapshot_id": snapshotID, "table": serial, "first_result": firstResult,
	}
	questions := map[string]map[string]any{
		"target": {"type": "choice",
			"instructions": "Pick the table row index that best matches the requested element on the current screen. Choose NONE if no candidate is useful. Never invent indices outside the table.",
			"criteria":     crit},
	}
	return state, questions
}

// ParseResolveAnswer valida Choice estricta → (idx|NONE, conf).
func ParseResolveAnswer(answer map[string]any, criteria map[string]any) (any, float64, error) {
	key, _, conf, err := jev.ValidateChoice(answer, criteria)
	if err != nil {
		return nil, 0, err
	}
	confF, ok := toFloat(answer["confidence"])
	if !ok {
		confF = conf
	}
	_ = conf
	if math.IsNaN(confF) || math.IsInf(confF, 0) || confF < 0.0 || confF > 1.0 {
		return nil, 0, &jev.JevHallucination{Msg: "TypeSafe returned an invalid choice distribution. (conf no finita o fuera de [0,1])"}
	}
	if key == "NONE" {
		return "NONE", confF, nil
	}
	var n int
	if _, err := fmt.Sscan(key, &n); err != nil {
		return nil, 0, &jev.JevHallucination{Msg: "target no numérico"}
	}
	return n, confF, nil
}

func toFloat(v any) (float64, bool) {
	switch t := v.(type) {
	case float64:
		return t, true
	case float32:
		return float64(t), true
	case int:
		return float64(t), true
	case int64:
		return float64(t), true
	}
	return 0, false
}

// AskFunc inyectable para tests (equiv. _ask).
type AskFunc func(state map[string]any, questions map[string]map[string]any) (map[string]jev.Answer, map[string]any, error)

// S1Unavailable resolve_element desactivado sin key S1 (spec §1.1).
// Nunca lleva idx utilizable; el stub {mock:true} no es resolución válida.
type S1Unavailable struct{ Msg string }

func (e *S1Unavailable) Error() string { return e.Msg }

// ResolveElement resuelve un elemento vía S1 (UNA Choice, sin goal global).
func ResolveElement(screenGoal string, serial []jev.SerialRow, snapshotID int64, currentApp string, firstResult any, ask AskFunc, tracker *cost.Tracker, runID string) (map[string]any, error) {
	// Sin key S1 el path director queda desactivado (spec ai-providers
	// §1.1): error honesto, nunca un idx inventado. El stub {mock:true}
	// de jev.Ask NO es una resolución válida y ningún tap/type puede
	// ejecutarse sobre él. S1 nunca lee JAV_AI_*: solo OPENROUTER_API_KEY.
	if jev.IsMock() {
		return nil, &S1Unavailable{Msg: "S1_UNAVAILABLE: resolve_element desactivado sin OPENROUTER_API_KEY; rellena OPENROUTER_API_KEY (S1 solo acepta esa key, nunca JAV_AI_API_KEY)"}
	}
	state, questions := BuildResolveState(screenGoal, serial, snapshotID, currentApp, firstResult)
	fn := ask
	if fn == nil {
		fn = jev.Ask
	}
	answers, usage, err := fn(state, questions)
	if err != nil {
		return nil, err
	}
	norm, ok := answers["target"]
	if !ok {
		return nil, &jev.JevError{Msg: "S1 no respondió target"}
	}
	criteria, _ := questions["target"]["criteria"].(map[string]any)
	var idx any
	var conf float64
	if norm.Key != "" || norm.Raw != nil {
		if _, ok := criteria[norm.Key]; !ok {
			return nil, &jev.JevHallucination{Msg: "TypeSafe returned an invalid choice distribution. (choice fuera de criteria)"}
		}
		conf = norm.Confidence
		if math.IsNaN(conf) || math.IsInf(conf, 0) || conf < 0.0 || conf > 1.0 {
			return nil, &jev.JevHallucination{Msg: "TypeSafe returned an invalid choice distribution. (conf no finita o fuera de [0,1])"}
		}
		if norm.Key == "NONE" {
			idx = "NONE"
		} else {
			var n int
			if _, err := fmt.Sscan(norm.Key, &n); err != nil {
				return nil, &jev.JevHallucination{Msg: "target no numérico"}
			}
			idx = n
		}
	} else {
		return nil, &jev.JevError{Msg: "S1 no respondió target"}
	}
	mock := false
	if norm.Raw != nil {
		if raw, ok := norm.Raw["mock"].(bool); ok && raw {
			mock = true
		}
	}
	if tracker == nil {
		tracker = cost.NewTracker(runID)
	}
	inTok, outTok, pcost := jev.UsageTokens(usage)
	stepCost := tracker.Track(cost.JevModelID(), inTok, outTok, nil, "s1", pcost)
	out := map[string]any{
		"idx": idx, "conf": conf, "snapshot_id": snapshotID,
		"usage": usage, "cost_usd": stepCost,
	}
	if mock {
		if um, _ := usage["mock"].(bool); um {
			mock = true
		}
		out["mock"] = true
	} else if um, _ := usage["mock"].(bool); um {
		out["mock"] = true
	}
	return out, nil
}

// --- TapIdx ---

// TapFunc inyectable (nodeID, snapshotID) → envelope Jam.
type TapFunc func(nodeID string, snapshotID int64) jam.Envelope

// TapIdx tapea por índice de tabla vigente (by_idx → node_id + validate).
func TapIdx(idx int, snapshotID int64, cands []normalizer.Candidate, screenH int, tap TapFunc) jam.Envelope {
	rows, byIdx := normalizer.BuildTable(cands, 0, screenH)
	_ = rows
	row, ok := byIdx[idx]
	var rp *normalizer.Row
	if ok {
		rp = &row
	}
	if bad := normalizer.ValidateTarget(rp, screenH); bad != nil {
		hint := "re-haz read_screen_state; el indice no matchea"
		return jam.Envelope{"ok": false, "verified": false,
			"evidence": map[string]any{"code": bad.Code, "error": bad.Error}, "hint": hint}
	}
	fn := tap
	if fn == nil {
		fn = func(nodeID string, snap int64) jam.Envelope {
			c, jerr := jam.Dial()
			if jerr != nil {
				return jam.JamFail(jerr)
			}
			defer c.Close()
			res, jerr := c.TapNode(nodeID, snap)
			if jerr != nil {
				return jam.JamFail(jerr)
			}
			return jam.OK(true, map[string]any{"node_id": res["node_id"], "via": res["via"]},
				"verifica el efecto con read_screen")
		}
	}
	return fn(row.ID, snapshotID)
}

// --- Clipboard host (equiv. tools/clipboard.py) ---

const ClipboardSlot = "clipboard"
const ViaDumpsys = "dumpsys"
const ViaPasteReadback = "paste-readback"
const ViaJamAPI = "jam-api"

var urlShapeRe = regexp.MustCompile(`https?://[^\s'"}\]]+`)
var primaryClipRe = regexp.MustCompile(`(?i)primary clip`)

func cleanURL(raw string) string {
	return strings.TrimRight(strings.TrimSpace(raw), ".,;)")
}

// ParseDumpsysClipboard extrae el primer enlace con forma del clip primario.
func ParseDumpsysClipboard(output string) string {
	if output == "" || !primaryClipRe.MatchString(output) {
		return ""
	}
	parts := primaryClipRe.Split(output, 2)
	if len(parts) < 2 {
		return ""
	}
	m := urlShapeRe.FindString(parts[1])
	return cleanURL(m)
}

// ClipboardError verificación por forma (nil = pasa).
func ClipboardError(text string) *normalizer.FailInfo {
	if text != "" && urlShapeRe.MatchString(text) {
		return nil
	}
	return &normalizer.FailInfo{Code: "CLIPBOARD_EMPTY",
		Error: "clipboard without link shape (empty or no https?://); copy first, do not invent content"}
}

// NewClipboardSlot slot opaco para pending_payloads (solo len+sha256 en forense).
func NewClipboardSlot(text string) map[string]any {
	sum := sha256.Sum256([]byte(text))
	return map[string]any{"text": text, "len": len(text),
		"sha256": hex.EncodeToString(sum[:]), "consumed": false}
}

// RunFunc hook inyectable para adb host (tests).
type RunFunc func(cmd []string) (string, error)

func defaultRun(cmd []string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, cmd[0], cmd[1:]...).Output()
	return string(out), err
}

// ReadClipboard lee el clipboard en el host adb y lo verifica por forma.
func ReadClipboard(run RunFunc, fallbackText string) jam.Envelope {
	if run == nil {
		run = defaultRun
	}
	text, via := "", ViaDumpsys
	out, err := run([]string{"adb", "shell", "dumpsys", "clipboard"})
	fbErr := ""
	if err != nil {
		fbErr = "adb dumpsys failed"
		out = ""
	}
	text = ParseDumpsysClipboard(out)
	if ClipboardError(text) != nil && fallbackText != "" {
		text, via = fallbackText, ViaPasteReadback
	}
	if bad := ClipboardError(text); bad != nil {
		hint := fbErr
		if hint == "" {
			hint = "copy the link first; do not invent content"
		}
		return jam.Envelope{"ok": false, "verified": false,
			"evidence": map[string]any{"code": bad.Code, "error": bad.Error, "via": via},
			"hint":     hint}
	}
	slot := NewClipboardSlot(text)
	return jam.OK(false, map[string]any{
		"text": text, "clipboard_len": slot["len"],
		"clipboard_sha256": slot["sha256"], "via": via,
	}, "inject as opaque slot 'clipboard' via ACTION_SET_TEXT")
}

// JamSetFunc hook inyectable para set_clipboard (tests).
type JamSetFunc func(text string) (map[string]any, error)

// SetClipboard escribe vía Jam ClipboardManager + read-back de forma.
func SetClipboard(text string, jamSet JamSetFunc, run RunFunc) jam.Envelope {
	if bad := ClipboardError(text); bad != nil {
		return jam.Envelope{"ok": false, "verified": false,
			"evidence": map[string]any{"code": bad.Code, "error": bad.Error, "via": ViaJamAPI},
			"hint":     "refuse to write without link shape; do not invent"}
	}
	var res map[string]any
	if jamSet != nil {
		r, err := jamSet(text)
		if err != nil {
			return clipboardUnsupported(err.Error())
		}
		res = r
	} else {
		c, jerr := jam.Dial()
		if jerr != nil {
			return clipboardUnsupported(jerr.Code + ": " + jerr.Message)
		}
		r, jerr := c.SetClipboard(text)
		c.Close()
		if jerr != nil {
			return clipboardUnsupported(jerr.Code + ": " + jerr.Message)
		}
		res = r
	}
	back := ReadClipboard(run, "")
	if ok, _ := back["ok"].(bool); !ok {
		ev, _ := back["evidence"].(map[string]any)
		code, _ := ev["code"].(string)
		msg, _ := ev["error"].(string)
		if code == "" {
			code = "CLIPBOARD_EMPTY"
		}
		return jam.Envelope{"ok": false, "verified": false,
			"evidence": map[string]any{"code": code, "error": msg, "via": ViaJamAPI},
			"hint":     "Jam escribio pero el read-back no verifica forma"}
	}
	slot := NewClipboardSlot(text)
	_ = res
	return jam.OK(true, map[string]any{
		"chars": len(text), "clipboard_len": slot["len"],
		"clipboard_sha256": slot["sha256"], "via": ViaJamAPI,
	}, "verificado por read-back; inyecta o pega en destino")
}

func clipboardUnsupported(msg string) jam.Envelope {
	if strings.Contains(msg, "METHOD_NOT_ALLOWED") {
		return jam.Envelope{"ok": false, "verified": false,
			"evidence": map[string]any{"code": "CLIPBOARD_UNSUPPORTED",
				"error": "jam-api-missing: " + msg, "via": ViaJamAPI},
			"hint": "Jam sin metodo set_clipboard; usa type_text directo con el texto verificado en host"}
	}
	return jam.Envelope{"ok": false, "verified": false,
		"evidence": map[string]any{"code": "CLIPBOARD_UNSUPPORTED",
			"error": "jam set_clipboard fallo: " + msg, "via": ViaJamAPI},
		"hint": "revisa conexion con Jam"}
}
