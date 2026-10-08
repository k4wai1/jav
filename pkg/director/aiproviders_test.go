package director

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jev"
)

// Cadena §2.1 en director (duplicada de cost por fachada): cada nivel gana.
func TestS2ModelChain(t *testing.T) {
	t.Setenv("JAV_AI_MODEL", "proveedor/modelo-a")
	t.Setenv("S2_MODEL", "custom/model")
	t.Setenv("GLM_MODEL", "other/model")
	if S2ModelID() != "proveedor/modelo-a" {
		t.Fatalf("JAV_AI_MODEL debe ganar: %s", S2ModelID())
	}
	t.Setenv("JAV_AI_MODEL", "")
	if S2ModelID() != "custom/model" {
		t.Fatalf("S2_MODEL segundo: %s", S2ModelID())
	}
	t.Setenv("S2_MODEL", "")
	if S2ModelID() != "other/model" {
		t.Fatalf("GLM_MODEL tercero: %s", S2ModelID())
	}
	t.Setenv("GLM_MODEL", "")
	if S2ModelID() != "z-ai/glm-5.3-flash" {
		t.Fatalf("default final: %s", S2ModelID())
	}
}

func TestS2BaseURLDefaultAndTrim(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "")
	if S2BaseURL() != "https://openrouter.ai/api/v1" {
		t.Fatalf("default base: %q", S2BaseURL())
	}
	if S2Endpoint() != "https://openrouter.ai/api/v1/chat/completions" {
		t.Fatalf("endpoint default: %q", S2Endpoint())
	}
	t.Setenv("JAV_AI_BASE_URL", "http://127.0.0.1:11434/v1/")
	if S2BaseURL() != "http://127.0.0.1:11434/v1" {
		t.Fatalf("trim slash: %q", S2BaseURL())
	}
	if S2Endpoint() != "http://127.0.0.1:11434/v1/chat/completions" {
		t.Fatalf("endpoint local: %q", S2Endpoint())
	}
}

func TestS2APIKeyPrecedence(t *testing.T) {
	t.Setenv("JAV_AI_API_KEY", "k-jav")
	t.Setenv("OPENROUTER_API_KEY", "k-or")
	if S2APIKey() != "k-jav" {
		t.Fatalf("JAV_AI_API_KEY manda: %q", S2APIKey())
	}
	t.Setenv("JAV_AI_API_KEY", "")
	if S2APIKey() != "k-or" {
		t.Fatalf("fallback OPENROUTER_API_KEY: %q", S2APIKey())
	}
	t.Setenv("OPENROUTER_API_KEY", "")
	if S2APIKey() != "" || !IsMockS2() {
		t.Fatalf("sin ninguna → vacía + mock: %q", S2APIKey())
	}
}

func TestLoopbackDetection(t *testing.T) {
	for _, u := range []string{
		"http://127.0.0.1:11434/v1", "http://127.0.0.1:8000/v1",
		"http://localhost:11434/v1", "http://[::1]:8000/v1",
	} {
		if !IsLoopbackURL(u) {
			t.Fatalf("loopback debe dar true: %s", u)
		}
	}
	for _, u := range []string{
		"https://openrouter.ai/api/v1", "https://api.openai.com/v1",
		"https://api.deepseek.com",
	} {
		if IsLoopbackURL(u) {
			t.Fatalf("remota no debe dar loopback: %s", u)
		}
	}
}

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

// Aceptación #4a: S2 contra base local sin key → comando válido parseado.
func TestS2LocalWithoutKeyParses(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			http.NotFound(w, r)
			return
		}
		if auth := r.Header.Get("Authorization"); auth != "" {
			http.Error(w, "no se espera auth en loopback sin key", 400)
			return
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		content := `{"command":"HINT","guidance_for_s1":"re-observe the screen","stop":false}`
		resp := map[string]any{
			"choices": []any{map[string]any{"message": map[string]any{"content": content}}},
			"usage":   map[string]any{"prompt_tokens": 10, "completion_tokens": 5},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer srv.Close()
	t.Setenv("JAV_AI_BASE_URL", srv.URL)
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_MODEL", "modelo-local-test")
	if S2APIKey() != "" {
		t.Fatalf("sin keys → vacía")
	}
	if !IsLoopbackBase() {
		t.Fatalf("httptest debe verse loopback: %s", S2BaseURL())
	}
	out, usage, err := Advise("goal", "reason", []string{"[0] Button ok"}, "", "", "", "", 60)
	if err != nil {
		t.Fatalf("local sin key debe parsear: %v", err)
	}
	if out["command"] != "HINT" {
		t.Fatalf("comando: %v", out)
	}
	if usage["in_tokens"] != 10 {
		t.Fatalf("usage: %v", usage)
	}
}

// Aceptación #4b: S2 contra base remota sin key → error honesto, nunca stub.
func TestS2RemoteWithoutKeyHonestError(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "https://openrouter.ai/api/v1")
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	_, _, err := Advise("goal", "reason", []string{"x"}, "", "", "", "", 60)
	if err == nil {
		t.Fatalf("remota sin key debe fallar, nunca stub silencioso")
	}
	if _, ok := err.(*S2AuthError); !ok {
		t.Fatalf("debe ser S2AuthError, dio %T: %v", err, err)
	}
	_, _, err = CompileGoal("goal", nil, "", "", 60)
	if _, ok := err.(*S2AuthError); !ok {
		t.Fatalf("compile remota sin key: %T %v", err, err)
	}
}
