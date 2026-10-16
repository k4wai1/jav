package jev

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
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

func withEndpoint(t *testing.T, url string) {
	t.Helper()
	prev := endpointURL
	endpointURL = url
	t.Cleanup(func() { endpointURL = prev })
}

func TestPostJSONRetriesEmptyEnvelope(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		if hits == 1 {
			w.WriteHeader(http.StatusOK)
			return
		}
		_, _ = w.Write([]byte(`{"answers":{}}`))
	}))
	defer srv.Close()
	withEndpoint(t, srv.URL)
	data, err := postJSON(map[string]any{"model": "x"})
	if err != nil || data == nil || hits != 2 {
		t.Fatalf("retry ante envelope vacío: hits=%d err=%v", hits, err)
	}
}

func TestPostJSONEmptyEnvelopeAlwaysFails(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	withEndpoint(t, srv.URL)
	_, err := postJSON(map[string]any{"model": "x"})
	if err == nil || err.Error() != "envelope S1 no-JSON" || hits != 2 {
		t.Fatalf("envelope vacío siempre: hits=%d err=%v", hits, err)
	}
}

func TestPostJSONTruncatedJSONRetries(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		_, _ = w.Write([]byte(`{"answers":`))
	}))
	defer srv.Close()
	withEndpoint(t, srv.URL)
	_, err := postJSON(map[string]any{"model": "x"})
	if err == nil || err.Error() != "envelope S1 no-JSON" || hits != 2 {
		t.Fatalf("json truncado: hits=%d err=%v", hits, err)
	}
}

func TestPostJSONNon2xxDoesNotRetry(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	withEndpoint(t, srv.URL)
	_, err := postJSON(map[string]any{"model": "x"})
	if err == nil || err.Error() != "red S1 http 500" || hits != 1 {
		t.Fatalf("no-2xx no reintenta: hits=%d err=%v", hits, err)
	}
}

func TestPostJSONTransportFailureStillWrapped(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	srv.Close()
	withEndpoint(t, srv.URL)
	start := time.Now()
	_, err := postJSON(map[string]any{"model": "x"})
	if err == nil || !strings.HasPrefix(err.Error(), "red S1 falló tras retry:") {
		t.Fatalf("transporte envuelto: err=%v", err)
	}
	if time.Since(start) < 400*time.Millisecond {
		t.Fatalf("debe reintentar con espera: %v", time.Since(start))
	}
}

func TestNormAnswerCarriesProbs(t *testing.T) {
	ans := map[string]any{
		"choice": "a", "confidence": 0.9,
		"probabilities": map[string]any{"a": 0.9, "b": 0.1},
	}
	q := map[string]any{"type": "choice", "criteria": criteria("a", "b")}
	a, err := normAnswer("target", q, ans)
	if err != nil || len(a.Probs) != 2 || a.Probs["a"] != 0.9 || a.Probs["a"] != a.P {
		t.Fatalf("Probs transportadas: %+v err=%v", a.Probs, err)
	}
}

func TestStubAndOtherKindsHaveNoProbs(t *testing.T) {
	if a := stubPick(map[string]any{"type": "choice", "criteria": criteria("x")}); a.Probs != nil {
		t.Fatalf("stub choice sin Probs: %+v", a.Probs)
	}
	an, err := normAnswer("n", map[string]any{"type": "noul"}, map[string]any{"noul": 0.9})
	if err != nil || an.Probs != nil {
		t.Fatalf("noul sin Probs: %+v %v", an.Probs, err)
	}
	as, err := normAnswer("s", map[string]any{"type": "score"}, map[string]any{"score": 3})
	if err != nil || as.Probs != nil {
		t.Fatalf("score sin Probs: %+v %v", as.Probs, err)
	}
}

func TestAskDecisionSanitizesNoMutate(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JEV_MODEL", "typesafe/jev-1.13")
	table := []SerialRow{{0, "Button", "top-left", "click", "×\n"}}
	_, _, err := AskDecision("goal", table, 3, AskDecisionOpts{})
	if err != nil {
		t.Fatalf("mock no debe fallar: %v", err)
	}
	if table[0][4] != "×\n" {
		t.Fatalf("no debe mutar la tabla de entrada: %q", table[0][4])
	}
}
