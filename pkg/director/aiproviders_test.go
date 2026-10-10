package director

import (
	"strings"
	"testing"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jev"
)

// Sin S2 interno: OpenCode/cliente externo ES el único Sistema 2. Este
// fichero solo conserva la aceptación S1 de resolve_element (sin key →
// error honesto, nunca idx utilizable). El slug S2 por OpenRouter (p.ej.
// deepseek/deepseek-chat) lo configura el director externo; aquí no hay
// provider S2 ni tests de base/modelo/key S2.

// Aceptación #3 (Fallback Soberano): resolve_element sin
// OPENROUTER_API_KEY → payload fallback honesto, nunca idx utilizable,
// nunca error fatal de Go. El ask inyectado ni siquiera debe llamarse.
func TestResolveWithoutS1KeyFails(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_API_KEY", "clave-s2-que-s1-debe-ignorar")
	t.Setenv("JAV_AI_MODEL", "proveedor/modelo")
	called := false
	ask := func(state map[string]any, qs map[string]map[string]any) (map[string]jev.Answer, map[string]any, error) {
		called = true
		return map[string]jev.Answer{"target": {Kind: "choice", Key: "0"}}, nil, nil
	}
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "ok"}}
	out, err := ResolveElement("Tap the ok row", serial, 9, "com.example", nil, ask, cost.NewTracker("r"), "r")
	if err != nil {
		t.Fatalf("fallback soberano nunca es error fatal: %v", err)
	}
	if out == nil {
		t.Fatalf("sin S1 key debe devolver fallback, no nil")
	}
	if ok, _ := out["ok"].(bool); ok {
		t.Fatalf("fallback debe ser ok:false: %v", out)
	}
	if out["idx"] != nil {
		t.Fatalf("sin idx utilizable: %v", out)
	}
	if fb, _ := out["fallback_required"].(bool); !fb {
		t.Fatalf("fallback_required debe ser true: %v", out)
	}
	reason, _ := out["reason"].(string)
	if !strings.Contains(reason, "S1_UNAVAILABLE") && !strings.Contains(reason, "JEV_UNAVAILABLE") {
		t.Fatalf("código honesto S1_UNAVAILABLE/JEV_UNAVAILABLE: %v", out)
	}
	if !strings.Contains(reason, "OPENROUTER_API_KEY") {
		t.Fatalf("hint de key: %v", out)
	}
	rec, _ := out["recovery_instruction"].(string)
	if !strings.Contains(rec, "Director examina candidates/render") {
		t.Fatalf("recovery_instruction de la directiva: %v", out)
	}
	if called {
		t.Fatalf("el ask no debe llamarse sin key (cero mutaciones)")
	}
}
