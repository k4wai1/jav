package director

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jam"
)

// Superficie S2 agnóstica OpenAI-compatible (spec docs/specs/ai-providers.md
// §2). Resuelve base/key/modelo desde el entorno y ejecuta
// `POST {base}/chat/completions`. Es PURA resolución: NO se cablea a ningún
// flujo existente (`resolve_element` es S1 y no la usa), NO escribe a stdout
// y NO toca el dispositivo. S1 nunca lee JAV_AI_*.

// S2DefaultBaseURL base por defecto (OpenRouter).
const S2DefaultBaseURL = "https://openrouter.ai/api/v1"

// s2Timeout 15 s (spec §2); un retry lo aplica el llamante si lo desea.
const s2Timeout = 15 * time.Second

// S2BaseURL base resuelta de JAV_AI_BASE_URL → config.ai_base_url (default
// OpenRouter), sin barra final.
func S2BaseURL() string {
	if b := strings.TrimRight(strings.TrimSpace(jam.AIBaseURL()), "/"); b != "" {
		return b
	}
	return S2DefaultBaseURL
}

// S2Endpoint URL completa de `chat/completions`.
func S2Endpoint() string { return S2BaseURL() + "/chat/completions" }

// S2Key key resuelta: JAV_AI_API_KEY → OPENROUTER_API_KEY → config. Opcional
// contra base local; obligatoria contra base remota (ver S2Config).
func S2Key() string {
	if k := strings.TrimSpace(jam.AIAPIKey()); k != "" {
		return k
	}
	return strings.TrimSpace(jam.OpenRouterAPIKey())
}

// S2IsLocalBase true si la base es loopback/localhost (auth opcional).
func S2IsLocalBase() bool {
	u, err := url.Parse(S2BaseURL())
	if err != nil {
		return false
	}
	host := u.Hostname()
	return host == "localhost" || host == "::1" ||
		host == "127.0.0.1" || strings.HasPrefix(host, "127.")
}

// S2NoKey error honesto: base remota sin ninguna key. Nunca stub silencioso.
type S2NoKey struct{ Base string }

func (e *S2NoKey) Error() string {
	return "S2_UNAVAILABLE: base remota (" + e.Base + ") sin key; define JAV_AI_API_KEY u OPENROUTER_API_KEY (spec ai-providers §2)"
}

// S2EmptyResponse error honesto: `choices[0].message.content` vacío o sin
// objeto JSON tras el parseo (spec §4).
type S2EmptyResponse struct{ Msg string }

func (e *S2EmptyResponse) Error() string { return e.Msg }

// S2BadCommand error honesto: el content no es un comando/objeto JSON.
type S2BadCommand struct{ Msg string }

func (e *S2BadCommand) Error() string { return e.Msg }

// S2Config resuelve (base, key, model, error). Sin key contra base local →
// permitido; sin key contra base remota → *S2NoKey.
func S2Config() (base, key, model string, err error) {
	base, key, model = S2BaseURL(), S2Key(), cost.S2ModelID()
	if key == "" && !S2IsLocalBase() {
		return base, key, model, &S2NoKey{Base: base}
	}
	return base, key, model, nil
}

// S2ChatMessage mensaje del payload OpenAI-compatible.
type S2ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// DoFunc transporte HTTP inyectable (tests).
type DoFunc func(*http.Request) (*http.Response, error)

// S2Chat ejecuta `POST {base}/chat/completions` y devuelve
// `choices[0].message.content`. `do == nil` usa `http.DefaultClient.Do`.
// Devuelve *S2NoKey (config), *S2EmptyResponse (content vacío) o un error de
// transporte/HTTP.
func S2Chat(ctx context.Context, messages []S2ChatMessage, temperature float64, maxTokens int, do DoFunc) (string, error) {
	_, key, model, err := S2Config()
	if err != nil {
		return "", err
	}
	if do == nil {
		do = http.DefaultClient.Do
	}
	if ctx == nil {
		ctx = context.Background()
	}
	payload := map[string]any{
		"model":       model,
		"messages":    messages,
		"temperature": temperature,
		"max_tokens":  maxTokens,
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, S2Endpoint(), bytes.NewReader(raw))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}
	resp, err := do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", &S2EmptyResponse{Msg: "S2 HTTP " + strconv.Itoa(resp.StatusCode) + ": " + strings.TrimSpace(string(body))}
	}
	return s2ParseContent(body)
}

// s2ParseContent extrae `choices[0].message.content`; vacío → *S2EmptyResponse.
func s2ParseContent(body []byte) (string, error) {
	var out struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return "", &S2EmptyResponse{Msg: "S2EmptyResponse: cuerpo no JSON: " + err.Error()}
	}
	if len(out.Choices) == 0 || strings.TrimSpace(out.Choices[0].Message.Content) == "" {
		return "", &S2EmptyResponse{Msg: "S2EmptyResponse: content vacío"}
	}
	return out.Choices[0].Message.Content, nil
}

// S2ParseCommand interpreta el content como comando/objeto JSON. Content no
// objeto o nulo → *S2BadCommand (spec §4).
func S2ParseCommand(content string) (map[string]any, error) {
	var cmd map[string]any
	dec := json.NewDecoder(strings.NewReader(content))
	if err := dec.Decode(&cmd); err != nil {
		return nil, &S2BadCommand{Msg: "S2BadCommand: content no es objeto JSON: " + err.Error()}
	}
	if cmd == nil {
		return nil, &S2BadCommand{Msg: "S2BadCommand: content nulo"}
	}
	return cmd, nil
}
