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

func TestBuildResolveStateEnrichesLabels(t *testing.T) {
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "9"}}
	state, questions := BuildResolveState("Tap nine", serial, 9, "com.example", nil)
	rows, ok := state["table"].([]jev.SerialRow)
	if !ok || len(rows) != 1 {
		t.Fatalf("table copiada: %v", state["table"])
	}
	if rows[0][4] != "9 [digit nine]" {
		t.Fatalf("label enriquecido: %v", rows[0][4])
	}
	if serial[0][4] != "9" {
		t.Fatalf("no debe mutar la entrada: %v", serial[0][4])
	}
	crit, _ := questions["target"]["criteria"].(map[string]any)
	if _, ok := crit["0"]; !ok {
		t.Fatalf("criteria conserva la clave 0: %v", crit)
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

func TestBuildResolveStateEnrichesLabelsZeroWidth(t *testing.T) {
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "\u200b9"}}
	state, _ := BuildResolveState("Tap nine", serial, 9, "com.example", nil)
	rows, ok := state["table"].([]jev.SerialRow)
	if !ok || len(rows) != 1 {
		t.Fatalf("table copiada: %v", state["table"])
	}
	if rows[0][4] != "9 [digit nine]" {
		t.Fatalf("zero-width debe sanearse antes de enriquecer: %q", rows[0][4])
	}
	if serial[0][4] != "\u200b9" {
		t.Fatalf("no debe mutar la entrada: %q", serial[0][4])
	}
}

func TestTopCandidatesOrder(t *testing.T) {
	got := TopCandidates(map[string]float64{"2": 0.4, "1": 0.4, "0": 0.2}, 3)
	want := []TopCandidate{{1, 0.4}, {2, 0.4}, {0, 0.2}}
	if len(got) != len(want) {
		t.Fatalf("orden/tope: %+v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("orden[%d]: got %+v want %+v", i, got[i], want[i])
		}
	}
	if TopCandidates(map[string]float64{"NONE": 0.9}, 3) != nil {
		t.Fatalf("NONE debe excluirse")
	}
	if TopCandidates(map[string]float64{}, 3) != nil {
		t.Fatalf("vacío debe ser nil")
	}
	if TopCandidates(map[string]float64{"999": 0.9}, 3) != nil {
		t.Fatalf("fuera de 0..253 debe ser nil")
	}
}

func TestResolveLowConfTopCandidates(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key-sin-red")
	serial := []jev.SerialRow{{0, "a", "top-left", "x", "a"}, {1, "b", "top-left", "x", "b"},
		{2, "c", "top-left", "x", "c"}, {3, "d", "top-left", "x", "d"}}
	probs := map[string]float64{"0": 0.55, "1": 0.30, "2": 0.10, "3": 0.05, "NONE": 0.0}
	out, err := ResolveElementWithTau("Tap a", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "0", Confidence: 0.40, Probs: probs}}, map[string]any{}, nil
		}, nil, "r-low", 0.70)
	if err != nil {
		t.Fatalf("nunca error fatal: %v", err)
	}
	if reason, _ := out["reason"].(string); !containsStr(reason, "LOW_CONF") {
		t.Fatalf("reason LOW_CONF: %v", out)
	}
	if _, ok := out["conf"]; !ok {
		t.Fatalf("conf debe conservarse: %v", out)
	}
	top, ok := out["top_candidates"].([]TopCandidate)
	if !ok || len(top) != 3 {
		t.Fatalf("top_candidates presente len 3: %v", out["top_candidates"])
	}
	want := []TopCandidate{{0, 0.55}, {1, 0.30}, {2, 0.10}}
	for i := range want {
		if top[i] != want[i] {
			t.Fatalf("top[%d]=%+v want %+v", i, top[i], want[i])
		}
	}
}

func TestResolveNoneTopCandidates(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key-sin-red")
	serial := []jev.SerialRow{{0, "a", "top-left", "x", "a"}}
	out, err := ResolveElement("Tap a", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "NONE", Confidence: 0.95,
				Probs: map[string]float64{"0": 0.05, "NONE": 0.95}}}, map[string]any{}, nil
		}, nil, "r-none")
	if err != nil {
		t.Fatalf("nunca error fatal: %v", err)
	}
	if reason, _ := out["reason"].(string); !containsStr(reason, "NO_TARGET") {
		t.Fatalf("reason NO_TARGET: %v", out)
	}
	top, _ := out["top_candidates"].([]TopCandidate)
	if len(top) != 1 || top[0].Idx != 0 || top[0].Prob != 0.05 {
		t.Fatalf("NONE excluido aun siendo máximo: %+v", out["top_candidates"])
	}
}

func TestResolveLowConfWithoutProbsKeepsCompat(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key-sin-red")
	serial := []jev.SerialRow{{0, "a", "top-left", "x", "a"}}
	out, err := ResolveElementWithTau("Tap a", serial, 7, "com.example", nil,
		func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "0", Confidence: 0.40}}, map[string]any{}, nil
		}, nil, "r-low", 0.70)
	if err != nil {
		t.Fatalf("nunca error fatal: %v", err)
	}
	if _, ok := out["top_candidates"]; ok {
		t.Fatalf("sin Probs no debe haber top_candidates: %v", out)
	}
	if reason, _ := out["reason"].(string); !containsStr(reason, "LOW_CONF") {
		t.Fatalf("reason LOW_CONF: %v", out)
	}
}

func TestResolveFallbacksWithoutTopCandidates(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key-sin-red")
	serial := []jev.SerialRow{{0, "a", "top-left", "x", "a"}, {1, "b", "top-left", "x", "b"}}
	cases := []struct {
		name string
		ask  AskFunc
	}{
		{"red", func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return nil, nil, &jev.JevError{Msg: "timeout"}
		}},
		{"envelope-vacio", func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{}, map[string]any{}, nil
		}},
		{"hallucination", func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
			return map[string]jev.Answer{"target": {Kind: "choice", Key: "99", Confidence: 0.9}}, map[string]any{}, nil
		}},
	}
	for _, c := range cases {
		out, err := ResolveElement("Tap a", serial, 7, "com.example", nil, c.ask, nil, "r-"+c.name)
		if err != nil {
			t.Fatalf("%s: nunca error fatal: %v", c.name, err)
		}
		if _, ok := out["top_candidates"]; ok {
			t.Fatalf("%s: no debe llevar top_candidates: %v", c.name, out)
		}
	}
	// Sin key S1: S1_UNAVAILABLE.
	t.Setenv("OPENROUTER_API_KEY", "")
	out, err := ResolveElement("Tap a", serial, 7, "com.example", nil, nil, nil, "r-nokey")
	if err != nil {
		t.Fatalf("sin key: nunca error fatal: %v", err)
	}
	if _, ok := out["top_candidates"]; ok {
		t.Fatalf("sin key: no debe llevar top_candidates: %v", out)
	}
}
