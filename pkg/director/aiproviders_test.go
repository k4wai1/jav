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

// Aceptación #3: resolve_element sin OPENROUTER_API_KEY → error honesto,
// nunca idx utilizable. El ask inyectado ni siquiera debe llamarse.
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
	if err == nil {
		t.Fatalf("sin S1 key debe fallar: %v", out)
	}
	msg := err.Error()
	if !strings.Contains(msg, "S1_UNAVAILABLE") && !strings.Contains(msg, "JEV_UNAVAILABLE") {
		t.Fatalf("código honesto S1_UNAVAILABLE/JEV_UNAVAILABLE: %v", err)
	}
	if !strings.Contains(msg, "OPENROUTER_API_KEY") {
		t.Fatalf("hint de key: %v", err)
	}
	if called {
		t.Fatalf("el ask no debe llamarse sin key (cero mutaciones)")
	}
	if out != nil {
		t.Fatalf("sin idx utilizable: %v", out)
	}
}
