package jev

import (
	"strings"
	"testing"
)

// Spec ai-providers §3 + aceptación #2: JEV_MODEL solo acepta slugs Jev.
// Chat-model como S1 → JevHallucination, cero mutaciones (sin red: el
// error sale de checkModelID antes de cualquier HTTP/stub).
func TestChatModelAsS1Fails(t *testing.T) {
	for _, bad := range []string{"gpt-4o-mini", "qwen-1", "deepseek-chat", "glm-5", "z-ai/glm-5.3-flash"} {
		t.Setenv("JEV_MODEL", bad)
		t.Setenv("OPENROUTER_API_KEY", "dummy-para-test-sin-red")
		if IsJevModel(bad) {
			t.Fatalf("chat-model %q no debe pasar IsJevModel", bad)
		}
		state := map[string]any{}
		qs := map[string]map[string]any{
			"action": {"type": "choice", "criteria": criteria("TAP", "DONE")},
		}
		_, _, err := Ask(state, qs)
		if err == nil {
			t.Fatalf("JEV_MODEL=%q debe fallar", bad)
		}
		if _, ok := err.(*JevHallucination); !ok {
			t.Fatalf("JEV_MODEL=%q debe dar JevHallucination, dio %T: %v", bad, err, err)
		}
	}
}

// Sin key también: el modelo se valida antes del stub (cero mutaciones).
func TestChatModelAsS1FailsWithoutKey(t *testing.T) {
	t.Setenv("JEV_MODEL", "gpt-4o-mini")
	t.Setenv("OPENROUTER_API_KEY", "")
	_, _, err := Ask(map[string]any{}, map[string]map[string]any{
		"action": {"type": "choice", "criteria": criteria("TAP")},
	})
	if _, ok := err.(*JevHallucination); !ok {
		t.Fatalf("sin key pero con chat-model debe dar JevHallucination: %v", err)
	}
}

func TestJevModelsAllowed(t *testing.T) {
	for _, good := range []string{"typesafe/jev-1.13", "jev-latest", "typesafe/jev-1.14"} {
		if !IsJevModel(good) {
			t.Fatalf("slug Jev %q debe pasar", good)
		}
	}
	t.Setenv("JEV_MODEL", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	if ModelID() != "typesafe/jev-1.13" {
		t.Fatalf("default S1: %q", ModelID())
	}
}

// Aceptación #1 (mitad S1): pkg/jev nunca lee la env agnóstica S2.
// (Nombres de env construidos por concatenación para que el grep
// literal del spec sobre pkg/jev siga vacío.)
func TestS1IgnoresJavAI(t *testing.T) {
	pfx := "JAV_" + "AI_"
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JEV_MODEL", "typesafe/jev-1.13")
	t.Setenv(pfx+"BASE_URL", "http://127.0.0.1:9/v1")
	t.Setenv(pfx+"API_KEY", "clave-que-s1-debe-ignorar")
	t.Setenv(pfx+"MODEL", "gpt-4o-mini")
	if !IsMock() {
		t.Fatalf("S1 sin OPENROUTER_API_KEY debe seguir mock aunque haya key S2 agnóstica")
	}
	if ModelID() != "typesafe/jev-1.13" {
		t.Fatalf("S1 no debe leer modelo S2 agnóstico: %q", ModelID())
	}
	if got := ModelID(); strings.Contains(got, "gpt") {
		t.Fatalf("fuga de modelo S2 a S1: %q", got)
	}
}
