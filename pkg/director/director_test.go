package director

import (
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

func TestResolveSovereignFallback(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key-sin-red")
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "ok"}, {1, "Button", "top-left", "click", "cancel"}}
	assertFallback := func(name string, out map[string]any, err error, wantReason string) {
		t.Helper()
		if err != nil {
			t.Fatalf("%s: nunca error fatal: %v", name, err)
		}
		if out == nil {
			t.Fatalf("%s: fallback no nil", name)
		}
		if ok, _ := out["ok"].(bool); ok {
			t.Fatalf("%s: ok debe ser false: %v", name, out)
		}
		if out["idx"] != nil {
			t.Fatalf("%s: idx debe ser null: %v", name, out)
		}
		if fb, _ := out["fallback_required"].(bool); !fb {
			t.Fatalf("%s: fallback_required true: %v", name, out)
		}
		reason, _ := out["reason"].(string)
		if reason == "" || !containsStr(reason, wantReason) {
			t.Fatalf("%s: reason con %q: %v", name, wantReason, out)
		}
		rec, _ := out["recovery_instruction"].(string)
		if !containsStr(rec, "Director examina candidates/render") {
			t.Fatalf("%s: recovery de la directiva: %v", name, out)
		}
		if _, ok := out["snapshot_id"]; !ok {
			t.Fatalf("%s: snapshot_id presente: %v", name, out)
		}
	}

	// Red: ask devuelve error.
	netErr := &jev.JevError{Msg: "red S1 falló tras retry: timeout"}
	out, err := ResolveElement("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return nil, nil, netErr
		}, nil, "r-net")
	assertFallback("red", out, err, "S1_NETWORK")

	// Envelope vacío: sin respuesta target.
	out, err = ResolveElement("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{}, map[string]any{}, nil
		}, nil, "r-empty")
	assertFallback("envelope-vacio", out, err, "S1_EMPTY_ENVELOPE")

	// Alucinación: clave fuera de criteria.
	out, err = ResolveElement("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "99", Confidence: 0.9}}, map[string]any{}, nil
		}, nil, "r-hallu")
	assertFallback("hallucination", out, err, "S1_HALLUCINATION")

	// conf<tau: fallback con conf visible.
	out, err = ResolveElementWithTau("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "0", Confidence: 0.40}}, map[string]any{}, nil
		}, nil, "r-low", 0.70)
	assertFallback("conf-baja", out, err, "LOW_CONF")

	// NONE: sin candidato útil.
	out, err = ResolveElement("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "NONE", Confidence: 0.95}}, map[string]any{}, nil
		}, nil, "r-none")
	assertFallback("none", out, err, "NO_TARGET")

	// Control: conf alta resuelve sin fallback.
	out, err = ResolveElement("Tap the ok row", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "1", Confidence: 0.90}}, map[string]any{}, nil
		}, nil, "r-ok")
	if err != nil {
		t.Fatalf("ok: sin error: %v", err)
	}
	if ok, _ := out["ok"].(bool); !ok {
		t.Fatalf("ok: ok true: %v", out)
	}
	if fb, _ := out["fallback_required"].(bool); fb {
		t.Fatalf("ok: sin fallback: %v", out)
	}
	if out["idx"] != 1 {
		t.Fatalf("ok: idx 1: %v", out)
	}
}

func containsStr(hay, needle string) bool {
	if len(needle) == 0 {
		return true
	}
	for i := 0; i+len(needle) <= len(hay); i++ {
		if hay[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
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
