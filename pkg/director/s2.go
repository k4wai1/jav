package director

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/jev"
	"github.com/k4wai1/jav/pkg/uitrack"
)

// Superficie S2 agnóstica OpenAI-compatible (spec docs/specs/ai-providers.md
// §2). Resuelve base/key/modelo desde el entorno y ejecuta
// `POST {base}/chat/completions`. v2.5.0: `resolve_element` la usa como
// RESPALDO de grounding cuando no hay S1 (o el operador fuerza
// JAV_RESOLVE_BACKEND=openai); el backend principal sigue siendo Jev. NO
// escribe a stdout y NO toca el dispositivo. S1 nunca lee JAV_AI_*.

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
// `choices[0].message.content`. `do == nil` usa `jam.HTTPClient.Do`
// (resolver DNS resiliente en Android/Termux).
// Devuelve *S2NoKey (config), *S2EmptyResponse (content vacío) o un error de
// transporte/HTTP.
func S2Chat(ctx context.Context, messages []S2ChatMessage, temperature float64, maxTokens int, do DoFunc) (string, error) {
	_, key, model, err := S2Config()
	if err != nil {
		return "", err
	}
	if do == nil {
		do = jam.HTTPClient.Do
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

// --- Grounding agnóstico en resolve_element (v2.5.0) --------------------

// S2CanResolve true si hay configuración EXPLÍCITA de LLM
// OpenAI-compatible para hacer grounding en `resolve_element`:
//   - base local explícita (Ollama/vLLM en loopback; key opcional), o
//   - key S2 + al menos un parámetro explícito (JAV_AI_API_KEY,
//     JAV_AI_BASE_URL o JAV_AI_MODEL; env o config).
//
// Sin nada configurado devuelve false y el path conserva el fallback
// S1_UNAVAILABLE: nunca se inventa un backend ni se sale a red a ciegas.
func S2CanResolve() bool {
	base := strings.TrimSpace(jam.AIBaseURL())
	if base != "" && S2IsLocalBase() {
		return true
	}
	if S2Key() == "" {
		return false
	}
	model := strings.TrimSpace(os.Getenv("JAV_AI_MODEL"))
	if model == "" {
		model = strings.TrimSpace(jam.LoadConfig().AIModel)
	}
	return strings.TrimSpace(jam.AIAPIKey()) != "" || base != "" || model != ""
}

// s2ResolveSystemPrompt contrato estricto del grounding: SOLO un objeto
// JSON con choice/confidence sobre índices de la tabla (nunca inventar).
const s2ResolveSystemPrompt = `You are a blind Android UI element resolver.
You receive a JSON object with "state" (screen_goal, current_app, snapshot_id, first_result and "table": rows [index, class, zone, flags, label]) and "question" (allowed choices in "criteria").
Pick the single table row index that best matches the screen goal on the CURRENT screen.
Rules:
- "choice" MUST be either an integer index present in the table or the string "NONE".
- Never invent indices outside the table; if nothing matches, use "NONE".
- "confidence" MUST be a finite number in [0,1].
Respond with ONLY one JSON object, no prose and no markdown fences:
{"choice": <int|"NONE">, "confidence": <float 0..1>}`

// ResolveElementWithS2 resuelve el elemento con un LLM OpenAI-compatible
// (respaldo agnóstico de `resolve_element`, v2.5.0). Reutiliza el estado
// ciego y el saneamiento de BuildResolveStateWithTried (labels, glifos,
// flags `tried`). Nunca devuelve un idx fuera de la tabla: cualquier
// anomalía es Fallback Soberano, nunca error fatal de Go.
func ResolveElementWithS2(ctx context.Context, screenGoal string, serial []jev.SerialRow, snapshotID int64, currentApp string, firstResult any, tau float64, do DoFunc) map[string]any {
	if tau <= 0 {
		tau = ResolveTau
	}
	state, questions := BuildResolveStateWithTried(screenGoal, serial, snapshotID,
		currentApp, firstResult, uitrack.CurrentTriedIdx())
	payload, err := json.Marshal(map[string]any{
		"state": state, "question": questions["target"],
	})
	if err != nil {
		return SovereignFallback("S2_UNAVAILABLE: no pude serializar el estado: "+err.Error(), snapshotID)
	}
	messages := []S2ChatMessage{
		{Role: "system", Content: s2ResolveSystemPrompt},
		{Role: "user", Content: string(payload)},
	}
	content, err := S2Chat(ctx, messages, 0.0, 128, do)
	if err != nil {
		return SovereignFallback("S2_UNAVAILABLE: "+err.Error(), snapshotID)
	}
	cmd, err := S2ParseCommand(stripJSONFences(content))
	if err != nil {
		return SovereignFallback("S2_HALLUCINATION: "+err.Error(), snapshotID)
	}
	criteria, _ := questions["target"]["criteria"].(map[string]any)
	key, ok := s2ChoiceKey(cmd["choice"], criteria)
	if !ok {
		return SovereignFallback("S2_HALLUCINATION: choice fuera de la tabla; nunca se inventan indices", snapshotID)
	}
	conf, ok := toFloat(cmd["confidence"])
	if !ok || math.IsNaN(conf) || math.IsInf(conf, 0) || conf < 0 || conf > 1 {
		return SovereignFallback("S2_HALLUCINATION: confidence no finita o fuera de [0,1]", snapshotID)
	}
	if key == "NONE" {
		return SovereignFallback("NO_TARGET: S2 eligió NONE; ningún candidato útil en esta pantalla", snapshotID)
	}
	if conf < tau {
		fb := SovereignFallback(fmt.Sprintf("LOW_CONF: conf %.3f < tau %.2f; no actuar", conf, tau), snapshotID)
		fb["conf"] = conf
		return fb
	}
	n, err := strconv.Atoi(key)
	if err != nil {
		return SovereignFallback("S2_HALLUCINATION: choice no numérico", snapshotID)
	}
	return map[string]any{
		"ok": true, "idx": n, "conf": conf, "snapshot_id": snapshotID,
		"fallback_required": false,
		"backend":           "openai-compat", "model": cost.S2ModelID(),
	}
}

// stripJSONFences limpia un fence markdown (```json … ```) antes de parsear.
func stripJSONFences(content string) string {
	t := strings.TrimSpace(content)
	if !strings.HasPrefix(t, "```") {
		return t
	}
	i := strings.IndexByte(t, '\n')
	if i < 0 {
		return ""
	}
	t = strings.TrimSpace(t[i+1:])
	if strings.HasSuffix(t, "```") {
		t = strings.TrimSpace(strings.TrimSuffix(t, "```"))
	}
	return t
}

// s2ChoiceKey valida `choice` contra criteria: "NONE" (cualquier caja) o
// un entero PRESENTE en la tabla (JSON lo entrega como float64). Cualquier
// otra cosa → false (alucinación, nunca idx utilizable).
func s2ChoiceKey(v any, criteria map[string]any) (string, bool) {
	switch t := v.(type) {
	case string:
		s := strings.TrimSpace(t)
		if strings.EqualFold(s, "NONE") {
			return "NONE", true
		}
		if _, ok := criteria[s]; ok {
			return s, true
		}
	case float64:
		if math.IsNaN(t) || math.IsInf(t, 0) || t != math.Trunc(t) {
			return "", false
		}
		s := strconv.Itoa(int(t))
		if _, ok := criteria[s]; ok {
			return s, true
		}
	case int:
		s := strconv.Itoa(t)
		if _, ok := criteria[s]; ok {
			return s, true
		}
	case int64:
		s := strconv.FormatInt(t, 10)
		if _, ok := criteria[s]; ok {
			return s, true
		}
	}
	return "", false
}
