package director

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
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
