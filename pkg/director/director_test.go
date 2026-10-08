package director

import (
	"strings"
	"testing"

	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/jev"
	"github.com/k4wai1/jav/pkg/normalizer"
)

func TestBuildResolveStateBlind(t *testing.T) {
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "ok"}}
	state, questions := BuildResolveState("Tap the ok row", serial, 9, "com.example", nil)
	for _, forbidden := range []string{"goal", "history", "s2_guidance", "package", "operator_verbatim"} {
		if _, ok := state[forbidden]; ok {
			t.Fatalf("state ciego no debe llevar %s: %v", forbidden, state)
		}
	}
	if _, ok := questions["target"]; !ok {
		t.Fatalf("solo pregunta target: %v", questions)
	}
}

func TestParseCommand(t *testing.T) {
	out, err := ParseCommand(map[string]any{"command": "TAP", "target": 3})
	if err != nil || out["target"] != 3 {
		t.Fatalf("TAP válido: %v %v", out, err)
	}
	if _, err := ParseCommand(map[string]any{"command": "TAP", "target": "NONE"}); err == nil {
		t.Fatalf("TAP con NONE debe fallar")
	}
	if _, err := ParseCommand(map[string]any{"command": "TYPE"}); err == nil {
		t.Fatalf("TYPE sin text debe fallar")
	}
	if _, err := ParseCommand(map[string]any{"command": "OPEN_APP", "package": "no-es-paquete"}); err == nil {
		t.Fatalf("package con mala forma debe fallar")
	}
}

func TestParseExecuteGoal(t *testing.T) {
	out, err := ParseExecuteGoal(map[string]any{
		"command": "EXECUTE_GOAL", "package": "com.example",
		"preloaded_inputs": map[string]any{"slot1": "texto exacto"},
	})
	if err != nil {
		t.Fatalf("plan válido: %v", err)
	}
	slots, _ := out["preloaded_inputs"].(map[string]string)
	if slots["slot1"] != "texto exacto" {
		t.Fatalf("slots: %v", out)
	}
}

func TestMaskPII(t *testing.T) {
	if got := MaskPII("llama al 123456 ahora"); !strings.Contains(got, "<digits:6>") {
		t.Fatalf("rachas ≥5 dígitos se enmascaran: %s", got)
	}
	if got := MaskPII("pin 1234"); strings.Contains(got, "<digits") {
		t.Fatalf("4 dígitos no se tocan: %s", got)
	}
}

func TestClipboardParse(t *testing.T) {
	out := "Primary clip: {https://example.com/x}"
	if got := ParseDumpsysClipboard(out); got != "https://example.com/x" {
		t.Fatalf("parse: %q", got)
	}
	if got := ParseDumpsysClipboard("sin seccion"); got != "" {
		t.Fatalf("sin sección debe ser vacío: %q", got)
	}
	if ClipboardError("") == nil || ClipboardError("https://a.b") != nil {
		t.Fatalf("verificación por forma https?://")
	}
}

func TestTapIdxValidates(t *testing.T) {
	cands := []normalizer.Candidate{
		{ID: "n1", Cls: "Button", Text: "ok", Clickable: true, Visible: true, Bounds: [4]int{10, 10, 50, 50}},
	}
	called := false
	env := TapIdx(0, 5, cands, 200, func(nodeID string, snap int64) jam.Envelope {
		called = true
		if nodeID != "n1" || snap != 5 {
			t.Fatalf("tap con by_idx: %s %d", nodeID, snap)
		}
		return jam.OK(true, map[string]any{}, "")
	})
	_ = env
	if !called {
		t.Fatalf("tap válido debe ejecutarse")
	}
	env = TapIdx(9, 5, cands, 200, nil)
	ev, _ := env["evidence"].(map[string]any)
	if ev["code"] != "SELECTOR_NOT_FOUND" {
		t.Fatalf("idx fuera de tabla: %v", env)
	}
}
