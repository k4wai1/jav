package director

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/k4wai1/jav/pkg/jev"
)

// Aceptación ai-providers §5 #4: S2 contra base local sin key → comando
// válido parseado; contra base remota sin key → error honesto (*S2NoKey).
func TestS2LocalBaseWithoutKeyParsesCommand(t *testing.T) {
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_MODEL", "local/model")

	var gotPath, gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["model"] != "local/model" {
			t.Errorf("modelo enviado: %v", body["model"])
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"{\"action\":\"TAP\",\"target\":\"0\"}"}}]}`))
	}))
	defer srv.Close()

	t.Setenv("JAV_AI_BASE_URL", srv.URL)
	if !S2IsLocalBase() {
		t.Fatalf("httptest debe ser base local: %s", S2BaseURL())
	}
	content, err := S2Chat(context.Background(), []S2ChatMessage{{Role: "user", Content: "hola"}}, 0, 64, nil)
	if err != nil {
		t.Fatalf("base local sin key no debe fallar: %v", err)
	}
	if gotPath != "/chat/completions" {
		t.Fatalf("endpoint inesperado: %s", gotPath)
	}
	if gotAuth != "" {
		t.Fatalf("sin key no debe mandar Authorization: %q", gotAuth)
	}
	cmd, err := S2ParseCommand(content)
	if err != nil {
		t.Fatalf("comando debe parsear: %v", err)
	}
	if cmd["action"] != "TAP" || cmd["target"] != "0" {
		t.Fatalf("comando inesperado: %v", cmd)
	}
}

func TestS2RemoteBaseWithoutKeyIsHonestError(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "https://example.invalid/api/v1")
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	if S2IsLocalBase() {
		t.Fatalf("base remota no es local")
	}
	if _, err := S2Chat(context.Background(), nil, 0, 0, nil); err == nil {
		t.Fatalf("base remota sin key debe fallar")
	} else if _, ok := err.(*S2NoKey); !ok {
		t.Fatalf("debe ser *S2NoKey, dio %T: %v", err, err)
	}
}

// Key: JAV_AI_API_KEY gana; fallback OPENROUTER_API_KEY; Authorization Bearer.
func TestS2KeyOrderAndBearer(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "https://example.invalid/v1")
	t.Setenv("OPENROUTER_API_KEY", "or-key")
	t.Setenv("JAV_AI_API_KEY", "jav-key")
	if S2Key() != "jav-key" {
		t.Fatalf("JAV_AI_API_KEY debe ganar: %s", S2Key())
	}
	t.Setenv("JAV_AI_API_KEY", "")
	if S2Key() != "or-key" {
		t.Fatalf("fallback OPENROUTER_API_KEY: %s", S2Key())
	}

	var gotAuth string
	do := func(req *http.Request) (*http.Response, error) {
		gotAuth = req.Header.Get("Authorization")
		rec := httptest.NewRecorder()
		rec.WriteString(`{"choices":[{"message":{"content":"{}"}}]}`)
		return rec.Result(), nil
	}
	if _, err := S2Chat(context.Background(), nil, 0, 0, do); err != nil {
		t.Fatalf("no debe fallar: %v", err)
	}
	if gotAuth != "Bearer or-key" {
		t.Fatalf("Authorization inesperado: %q", gotAuth)
	}
}

// Aceptación §5 #5: la cadena §2.1 alimenta el modelo S2 de la config.
func TestS2ConfigUsesModelChain(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "http://127.0.0.1:11434/v1")
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_MODEL", "proveedor/modelo-a")
	t.Setenv("S2_MODEL", "custom/model")
	if _, _, model, err := S2Config(); err != nil || model != "proveedor/modelo-a" {
		t.Fatalf("JAV_AI_MODEL debe ganar: %q err=%v", model, err)
	}
	t.Setenv("JAV_AI_MODEL", "")
	if _, _, model, _ := S2Config(); model != "custom/model" {
		t.Fatalf("vacío JAV_AI_MODEL → S2_MODEL: %q", model)
	}
	t.Setenv("S2_MODEL", "")
	t.Setenv("GLM_MODEL", "other/model")
	if _, _, model, _ := S2Config(); model != "other/model" {
		t.Fatalf("vacío JAV_AI+S2 → GLM_MODEL: %q", model)
	}
	t.Setenv("GLM_MODEL", "")
	if _, _, model, _ := S2Config(); model != "z-ai/glm-5.3-flash" {
		t.Fatalf("todo vacío → default: %q", model)
	}
}

// Content vacío / no objeto → errores honestos.
func TestS2ErrorsHonest(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "http://127.0.0.1:1/v1")
	t.Setenv("JAV_AI_API_KEY", "")
	if _, err := s2ParseContent([]byte(`{"choices":[]}`)); err == nil {
		t.Fatalf("choices vacío debe fallar")
	} else if _, ok := err.(*S2EmptyResponse); !ok {
		t.Fatalf("debe ser *S2EmptyResponse, dio %T", err)
	}
	if _, err := S2ParseCommand("no-json"); err == nil {
		t.Fatalf("comando no JSON debe fallar")
	} else if _, ok := err.(*S2BadCommand); !ok {
		t.Fatalf("debe ser *S2BadCommand, dio %T", err)
	}
	if _, err := S2ParseCommand("null"); err == nil {
		t.Fatalf("null debe fallar")
	}
}

func TestS2EndpointDefault(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "")
	if S2BaseURL() != S2DefaultBaseURL {
		t.Fatalf("default base: %s", S2BaseURL())
	}
	if !strings.HasSuffix(S2Endpoint(), "/chat/completions") {
		t.Fatalf("endpoint: %s", S2Endpoint())
	}
}

// --- v2.5.0: grounding agnóstico en resolve_element ---------------------

// s2Server sirve un `chat/completions` local que devuelve `content` fijo.
func s2Server(t *testing.T, content string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"choices": []any{map[string]any{
				"message": map[string]any{"content": content},
			}},
		})
	}))
	t.Cleanup(srv.Close)
	return srv
}

// pointS2At fija una base local explícita (sin key) y el modelo.
func pointS2At(t *testing.T, base string) {
	t.Helper()
	t.Setenv("JAV_AI_BASE_URL", base)
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_MODEL", "local/model")
}

func s2Serial() []jev.SerialRow {
	return []jev.SerialRow{
		{0, "Button", "top-left", "click", "ok"},
		{1, "Button", "top-left", "click", "cancel"},
	}
}

func TestS2CanResolveRequiresExplicitConfig(t *testing.T) {
	t.Setenv("JAV_AI_BASE_URL", "")
	t.Setenv("JAV_AI_API_KEY", "")
	t.Setenv("OPENROUTER_API_KEY", "")
	t.Setenv("JAV_AI_MODEL", "")
	if S2CanResolve() {
		t.Fatalf("sin config explícita S2CanResolve debe ser false")
	}
	// Base local explícita sin key → groundable.
	pointS2At(t, "http://127.0.0.1:11434/v1")
	if !S2CanResolve() {
		t.Fatalf("base local explícita debe permitir grounding")
	}
	// Key + modelo remotos → groundable.
	t.Setenv("JAV_AI_BASE_URL", "https://example.invalid/v1")
	t.Setenv("JAV_AI_API_KEY", "k")
	if !S2CanResolve() {
		t.Fatalf("key+modelo explícitos deben permitir grounding")
	}
}

func TestResolveElementWithS2Success(t *testing.T) {
	cases := map[string]string{
		"plain":  `{"choice": 1, "confidence": 0.92}`,
		"fenced": "```json\n{\"choice\": 1, \"confidence\": 0.92}\n```",
	}
	for name, content := range cases {
		t.Run(name, func(t *testing.T) {
			srv := s2Server(t, content)
			pointS2At(t, srv.URL)
			out := ResolveElementWithS2(context.Background(), "Tap cancel", s2Serial(),
				9, "com.example", nil, 0.70, nil)
			if ok, _ := out["ok"].(bool); !ok {
				t.Fatalf("%s: ok true: %v", name, out)
			}
			if out["idx"] != 1 {
				t.Fatalf("%s: idx 1: %v", name, out)
			}
			if out["backend"] != "openai-compat" {
				t.Fatalf("%s: backend: %v", name, out["backend"])
			}
			if out["model"] != "local/model" {
				t.Fatalf("%s: model: %v", name, out["model"])
			}
			if fb, _ := out["fallback_required"].(bool); fb {
				t.Fatalf("%s: sin fallback: %v", name, out)
			}
		})
	}
}

func TestResolveElementWithS2LowConfAndNone(t *testing.T) {
	cases := []struct {
		name       string
		content    string
		wantReason string
		wantConf   bool
	}{
		{"low-conf", `{"choice": 0, "confidence": 0.40}`, "LOW_CONF", true},
		{"none", `{"choice": "NONE", "confidence": 0.90}`, "NO_TARGET", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			srv := s2Server(t, c.content)
			pointS2At(t, srv.URL)
			out := ResolveElementWithS2(context.Background(), "Tap cancel", s2Serial(),
				9, "com.example", nil, 0.70, nil)
			if ok, _ := out["ok"].(bool); ok {
				t.Fatalf("%s: ok debe ser false: %v", c.name, out)
			}
			if out["idx"] != nil {
				t.Fatalf("%s: idx debe ser nil: %v", c.name, out)
			}
			if fb, _ := out["fallback_required"].(bool); !fb {
				t.Fatalf("%s: fallback_required true: %v", c.name, out)
			}
			reason, _ := out["reason"].(string)
			if !strings.Contains(reason, c.wantReason) {
				t.Fatalf("%s: reason con %q: %v", c.name, c.wantReason, out)
			}
			_, hasConf := out["conf"]
			if hasConf != c.wantConf {
				t.Fatalf("%s: conf presente=%v, esperado %v: %v", c.name, hasConf, c.wantConf, out)
			}
		})
	}
}

func TestResolveElementWithS2Hallucination(t *testing.T) {
	cases := map[string]string{
		"index-out-of-table": `{"choice": 99, "confidence": 0.9}`,
		"invalid-json":       "not-json",
		"bad-confidence":     `{"choice": 0, "confidence": 2}`,
	}
	for name, content := range cases {
		t.Run(name, func(t *testing.T) {
			srv := s2Server(t, content)
			pointS2At(t, srv.URL)
			out := ResolveElementWithS2(context.Background(), "Tap cancel", s2Serial(),
				9, "com.example", nil, 0.70, nil)
			if _, usable := out["idx"]; usable && out["idx"] != nil {
				t.Fatalf("%s: nunca idx utilizable: %v", name, out)
			}
			reason, _ := out["reason"].(string)
			if !strings.Contains(reason, "S2_HALLUCINATION") {
				t.Fatalf("%s: reason S2_HALLUCINATION: %v", name, out)
			}
		})
	}
}

// Sin key S1 y con base local: ResolveElement (ask nil) delega en S2.
func TestResolveElementDelegatesToS2WhenNoS1(t *testing.T) {
	srv := s2Server(t, `{"choice": 1, "confidence": 0.90}`)
	pointS2At(t, srv.URL)
	out, err := ResolveElement("Tap cancel", s2Serial(), 9, "com.example", nil,
		nil, nil, "r-s2")
	if err != nil {
		t.Fatalf("nunca error fatal: %v", err)
	}
	if ok, _ := out["ok"].(bool); !ok {
		t.Fatalf("debe resolver vía S2: %v", out)
	}
	if out["backend"] != "openai-compat" || out["idx"] != 1 {
		t.Fatalf("backend/idx inesperados: %v", out)
	}
}
