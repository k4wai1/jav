package jev

import (
	"testing"
)

func criteria(keys ...string) map[string]any {
	m := map[string]any{}
	for _, k := range keys {
		m[k] = k
	}
	return m
}

func TestValidateChoiceOK(t *testing.T) {
	ans := map[string]any{
		"choice": "a", "confidence": 0.9,
		"probabilities": map[string]any{"a": 0.9, "b": 0.1},
	}
	key, probs, conf, err := ValidateChoice(ans, criteria("a", "b"))
	if err != nil || key != "a" || conf != 0.9 || probs["a"] != 0.9 {
		t.Fatalf("válida debe pasar: %v %v", key, err)
	}
}

func TestValidateChoiceRejects(t *testing.T) {
	cases := []map[string]any{
		{"choice": "z", "confidence": 0.9, "probabilities": map[string]any{"a": 0.9, "b": 0.1}},
		{"choice": "a", "confidence": 0.9, "probabilities": map[string]any{"a": 0.9}},
		{"choice": "a", "confidence": 0.9, "probabilities": map[string]any{"a": 0.5, "b": 0.3}},
		{"choice": "b", "confidence": 0.9, "probabilities": map[string]any{"a": 0.9, "b": 0.1}},
		{"choice": "a", "confidence": 2.0, "probabilities": map[string]any{"a": 0.9, "b": 0.1}},
		{"choice": "a", "probabilities": map[string]any{"a": 0.9, "b": 0.1}},
	}
	for i, ans := range cases {
		if _, _, _, err := ValidateChoice(ans, criteria("a", "b")); err == nil {
			t.Fatalf("caso %d debe fallar", i)
		}
	}
}

func TestAskStubWithoutKey(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "")
	if !IsMock() {
		t.Fatalf("sin clave debe ser mock")
	}
	state := map[string]any{}
	qs := map[string]map[string]any{
		"action": {"type": "choice", "criteria": criteria("TAP", "DONE")},
	}
	answers, usage, err := Ask(state, qs)
	if err != nil || answers["action"].Raw["mock"] != true || usage["mock"] != true {
		t.Fatalf("stub honesto: %+v %v %v", answers, usage, err)
	}
}

func TestAskDecisionDoesNotMutateTable(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JEV_MODEL", "typesafe/jev-1.13")
	table := []SerialRow{{0, "Button", "top-left", "click", "×"}}
	_, _, err := AskDecision("goal", table, 3, AskDecisionOpts{})
	if err != nil {
		t.Fatalf("mock no debe fallar: %v", err)
	}
	if table[0][4] != "×" {
		t.Fatalf("no debe mutar la tabla de entrada: %v", table[0][4])
	}
}
