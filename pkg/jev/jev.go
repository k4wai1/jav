package jev

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/k4wai1/jav/pkg/normalizer"
)

// Cliente S1 vía OpenRouter (equiv. jev_client.py).
// ask batch + ask_decision single-pass; validateChoice estricta.

const Endpoint = "https://openrouter.ai/api/alpha/decisions"
const Timeout = 3 * time.Second

const ProbSumTol = 0.025
const ArgmaxEps = 1e-6

var DecisionActions = []string{"TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP", "BACK", "DONE", "ESCALATE"}

// JevError fallo genérico S1.
type JevError struct{ Msg string }

func (e *JevError) Error() string { return e.Msg }

// JevHallucination clave/target fuera de criteria o distribución inválida.
type JevHallucination struct{ Msg string }

func (e *JevHallucination) Error() string { return e.Msg }

// ModelID modelo S1 (env JEV_MODEL).
func ModelID() string {
	if m := os.Getenv("JEV_MODEL"); m != "" {
		return m
	}
	return "typesafe/jev-1.13"
}

// IsJevModel true solo para slugs Jev documentados (spec ai-providers §3).
// Válidos: typesafe/jev-1.13 (OpenRouter decisions) y jev-latest (API
// oficial TypeSafe, swap futuro). Se acepta el prefijo typesafe/jev-
// para menores futuros sin romper. Cualquier chat-model
// OpenAI-compatible (gpt-4o-mini, qwen-*, deepseek-*, glm-*, …) → false:
// no exponen la API de decisiones y jamás pasan ValidateChoice.
// S1 solo lee JEV_MODEL y OPENROUTER_API_KEY (nunca env agnóstica S2).
func IsJevModel(m string) bool {
	if m == "typesafe/jev-1.13" || m == "jev-latest" {
		return true
	}
	return strings.HasPrefix(m, "typesafe/jev-")
}

// checkModelID devuelve JevHallucination si JEV_MODEL no es un slug Jev.
// Se llama al inicio de Ask, antes de cualquier red/stub: cero mutaciones.
func checkModelID() error {
	m := ModelID()
	if IsJevModel(m) {
		return nil
	}
	return &JevHallucination{Msg: "JEV_MODEL " + m + " no expone la API de decisiones (S1 es Choice/Noul, no chat-model); usa typesafe/jev-1.13"}
}

// IsMock true sin clave (stub honesto {mock:true}).
func IsMock() bool { return os.Getenv("OPENROUTER_API_KEY") == "" }

// Answer normalizada: choice -> clave; noul -> true/false; score -> número.
type Answer struct {
	Kind       string // "choice" | "noul" | "score"
	Key        string
	P          float64
	Confidence float64
	Raw        map[string]any
}

func stubPick(q map[string]any) Answer {
	kind, _ := q["type"].(string)
	crit, _ := q["criteria"].(map[string]any)
	switch kind {
	case "noul":
		return Answer{Kind: "noul", Key: "true", P: 1.0, Confidence: 1.0, Raw: map[string]any{"mock": true}}
	case "score":
		key := "1"
		if crit != nil {
			for k := range crit {
				key = k
				break
			}
		}
		if list, ok := q["criteria"].([]any); ok && len(list) > 0 {
			if s, ok := list[len(list)-1].(string); ok {
				key = s
			}
		}
		return Answer{Kind: "score", Key: key, P: 1.0, Confidence: 1.0, Raw: map[string]any{"mock": true}}
	default:
		key := ""
		if crit != nil {
			for k := range crit {
				key = k
				break
			}
		}
		return Answer{Kind: "choice", Key: key, P: 1.0, Confidence: 1.0, Raw: map[string]any{"mock": true}}
	}
}

func finite01(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0.0 && v <= 1.0 }

func toFloat(v any) (float64, bool) {
	switch t := v.(type) {
	case float64:
		return t, true
	case float32:
		return float64(t), true
	case int:
		return float64(t), true
	case int64:
		return float64(t), true
	case json.Number:
		f, err := t.Float64()
		return f, err == nil
	}
	return 0, false
}

// ValidateChoice valida distribución choice estricta (patrón M1).
// Exige choice ∈ criteria, probabilities dict completa, conf/probs
// finitas [0,1], suma ±0.025, probs[choice] es argmax. Fallo → hallucination.
func ValidateChoice(answer map[string]any, criteria map[string]any) (string, map[string]float64, float64, error) {
	invalid := func(detail string) error {
		return &JevHallucination{Msg: "TypeSafe returned an invalid choice distribution. (" + detail + ")"}
	}
	if answer == nil {
		return "", nil, 0, invalid("answer no es objeto")
	}
	var choice string
	if c, ok := answer["choice"].(string); ok {
		choice = c
	} else if c, ok := answer["selected"].(string); ok {
		choice = c
	} else if c, ok := answer["value"].(string); ok {
		choice = c
	}
	if _, ok := criteria[choice]; !ok || choice == "" {
		if choice == "" && len(criteria) == 0 {
			return "", nil, 0, invalid("criteria vacío")
		}
		return "", nil, 0, invalid("choice fuera de criteria")
	}
	probsRaw, ok := answer["probabilities"].(map[string]any)
	if !ok {
		return "", nil, 0, invalid("probabilities ausente o no-dict")
	}
	if len(probsRaw) != len(criteria) {
		missing := false
		for k := range criteria {
			if _, ok := probsRaw[k]; !ok {
				missing = true
				break
			}
		}
		if missing {
			return "", nil, 0, invalid("probs incompleta")
		}
		return "", nil, 0, invalid("probs incompleta")
	}
	for k := range criteria {
		if _, ok := probsRaw[k]; !ok {
			return "", nil, 0, invalid("probs incompleta")
		}
	}
	conf, ok := toFloat(answer["confidence"])
	if !ok {
		return "", nil, 0, invalid("confidence no numérica")
	}
	probs := make(map[string]float64, len(probsRaw))
	for k, v := range probsRaw {
		f, ok := toFloat(v)
		if !ok {
			return "", nil, 0, invalid("probs no numéricas")
		}
		probs[k] = f
	}
	if !finite01(conf) {
		return "", nil, 0, invalid("confidence no finita o fuera de [0,1]")
	}
	for _, v := range probs {
		if !finite01(v) {
			return "", nil, 0, invalid("probs no finitas o fuera de [0,1]")
		}
	}
	sum := 0.0
	max := math.Inf(-1)
	for _, v := range probs {
		sum += v
		if v > max {
			max = v
		}
	}
	if math.Abs(sum-1.0) > ProbSumTol {
		return "", nil, 0, invalid("suma fuera de tolerancia")
	}
	if probs[choice]+ArgmaxEps < max {
		return "", nil, 0, invalid("choice no es argmax")
	}
	return choice, probs, conf, nil
}

func normAnswer(name string, q, ans map[string]any) (Answer, error) {
	kind, _ := q["type"].(string)
	critRaw := q["criteria"]
	switch kind {
	case "choice":
		crit := map[string]any{}
		if m, ok := critRaw.(map[string]any); ok {
			crit = m
		}
		key, probs, conf, err := ValidateChoice(ans, crit)
		if err != nil {
			return Answer{}, err
		}
		return Answer{Kind: "choice", Key: key, P: probs[key], Confidence: conf, Raw: ans}, nil
	case "noul":
		p := 0.0
		if v, ok := toFloat(ans["noul"]); ok {
			p = v
		} else if v, ok := toFloat(ans["p"]); ok {
			p = v
		}
		key := "false"
		if p >= 0.5 {
			key = "true"
		}
		return Answer{Kind: "noul", Key: key, P: p, Confidence: math.Abs(p-0.5) * 2, Raw: ans}, nil
	case "score":
		for _, k := range []string{"score", "value", "position", "level"} {
			if v, ok := toFloat(ans[k]); ok {
				return Answer{Kind: "score", Key: fmt.Sprint(v), P: v, Confidence: 1.0, Raw: ans}, nil
			}
		}
		slog.Warn("jev score con forma desconocida")
		return Answer{Kind: "score", Key: "?", P: 0, Confidence: 0, Raw: ans}, nil
	}
	return Answer{}, &JevError{Msg: name + ": tipo de pregunta desconocido"}
}

func postJSON(payload map[string]any) (map[string]any, error) {
	key := os.Getenv("OPENROUTER_API_KEY")
	var last error
	for attempt := 0; attempt < 2; attempt++ {
		ctx, cancel := context.WithTimeout(context.Background(), Timeout)
		body, _ := json.Marshal(payload)
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, Endpoint, bytes.NewReader(body))
		if err != nil {
			cancel()
			return nil, err
		}
		req.Header.Set("Authorization", "Bearer "+key)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("HTTP-Referer", "https://github.com/jev-android-mcp")
		req.Header.Set("X-Title", "jam-loop")
		resp, err := http.DefaultClient.Do(req)
		cancel()
		if err != nil {
			last = err
			time.Sleep(500 * time.Millisecond)
			continue
		}
		var data map[string]any
		decErr := json.NewDecoder(resp.Body).Decode(&data)
		_ = resp.Body.Close()
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return nil, &JevError{Msg: fmt.Sprintf("red S1 http %d", resp.StatusCode)}
		}
		if decErr != nil {
			return nil, &JevError{Msg: "envelope S1 no-JSON"}
		}
		return data, nil
	}
	return nil, &JevError{Msg: fmt.Sprintf("red S1 falló tras retry: %v", last)}
}

// Ask una request con TODAS las preguntas (batch). Devuelve (answers, usage).
func Ask(state map[string]any, questions map[string]map[string]any) (map[string]Answer, map[string]any, error) {
	if err := checkModelID(); err != nil {
		return nil, nil, err
	}
	if IsMock() {
		slog.Info("jev stub (sin clave): happy-path")
		out := make(map[string]Answer, len(questions))
		for n, q := range questions {
			out[n] = stubPick(q)
		}
		return out, map[string]any{"cost": 0.0, "mock": true}, nil
	}
	body := map[string]any{"model": ModelID(), "state": state, "questions": questions}
	data, err := postJSON(body)
	if err != nil {
		return nil, nil, err
	}
	rawAnswers, _ := data["answers"].(map[string]any)
	usage, _ := data["usage"].(map[string]any)
	if usage == nil {
		usage = map[string]any{}
	}
	out := make(map[string]Answer, len(questions))
	for name, q := range questions {
		raw, ok := rawAnswers[name].(map[string]any)
		if !ok {
			return nil, nil, &JevError{Msg: "S1 no respondió " + name}
		}
		norm, err := normAnswer(name, q, raw)
		if err != nil {
			return nil, nil, err
		}
		out[name] = norm
	}
	return out, usage, nil
}

// UsageTokens (in, out, providerCost|nil) desde usage heterogéneo.
func UsageTokens(usage map[string]any) (int, int, *float64) {
	if usage == nil {
		return 0, 0, nil
	}
	var inTok, outTok int
	if v, ok := toFloat(usage["in_tokens"]); ok {
		inTok = int(v)
	} else if v, ok := toFloat(usage["prompt_tokens"]); ok {
		inTok = int(v)
	}
	if v, ok := toFloat(usage["out_tokens"]); ok {
		outTok = int(v)
	} else if v, ok := toFloat(usage["completion_tokens"]); ok {
		outTok = int(v)
	}
	var pcost *float64
	if v, ok := toFloat(usage["cost"]); ok {
		pcost = &v
	}
	return inTok, outTok, pcost
}

// SerialRow fila serializada [idx,class_short,zone,flags,label].
type SerialRow = []any

// AskDecision single-pass S1: 1 llamada -> {action,target,needs_system_2,conf}.
func AskDecision(goal string, table []SerialRow, snapshotID int64, opts AskDecisionOpts) (map[string]any, map[string]any, error) {
	serial := make([]SerialRow, 0, len(table))
	for _, r := range table {
		cp := make(SerialRow, len(r))
		copy(cp, r)
		if len(cp) > 4 {
			if s, ok := cp[4].(string); ok {
				cp[4] = normalizer.FormatCandidateLabel(s)
			}
		}
		serial = append(serial, cp)
	}
	screen := opts.ScreenGoal
	if screen == "" {
		screen = goal
	}
	targetKeys := make([]string, 0, len(serial)+1)
	for _, r := range serial {
		if len(r) > 0 {
			targetKeys = append(targetKeys, fmt.Sprint(r[0]))
		}
	}
	targetKeys = append(targetKeys, "NONE")
	ffView := map[string]any{"label": "none", "holds": "empty"}
	if opts.FocusedField != nil {
		label, _ := opts.FocusedField["label"].(string)
		if label == "" {
			label = "none"
		}
		holds, _ := opts.FocusedField["holds"].(string)
		if holds == "" {
			holds = "empty"
		}
		ffView = map[string]any{"label": label, "holds": holds}
	}
	state := map[string]any{
		"goal": goal, "screen_goal": screen,
		"operator_verbatim": opts.ScreenGoal == "",
		"current_app":       opts.CurrentApp, "snapshot_id": snapshotID,
		"table": serial, "first_result": opts.FirstResult,
		"focused_field": ffView, "history": opts.HistorySummary,
		"s2_guidance": opts.S2Guidance,
	}
	actionCrit := map[string]any{}
	for _, a := range DecisionActions {
		actionCrit[a] = a
	}
	targetCrit := map[string]any{}
	for _, k := range targetKeys {
		targetCrit[k] = k
	}
	questions := map[string]map[string]any{
		"action": {"type": "choice",
			"instructions": "Pick ONE primitive to advance the goal.",
			"criteria":     actionCrit},
		"target": {"type": "choice",
			"instructions": "Target table row index. NONE if the action needs no node.",
			"criteria":     targetCrit},
		"needs_system_2": {"type": "noul",
			"instructions": "Does this step require System-2 open-text composition?"},
	}
	answers, usage, err := Ask(state, questions)
	if err != nil {
		return nil, nil, err
	}
	aAction := answers["action"]
	aTarget := answers["target"]
	aS2 := answers["needs_system_2"]
	tgt := aTarget.Key
	confRaw := math.Min(aAction.Confidence, aTarget.Confidence)
	if math.IsNaN(confRaw) || math.IsInf(confRaw, 0) {
		return nil, nil, &JevHallucination{Msg: "TypeSafe returned an invalid choice distribution. (conf no finita)"}
	}
	decision := map[string]any{
		"action": aAction.Key, "target": tgt,
		"needs_system_2": aS2.Key == "true",
		"conf":           confRaw, "type_text": "",
	}
	if tgt != "NONE" {
		var n int
		if _, err := fmt.Sscan(tgt, &n); err == nil {
			decision["target"] = n
		}
	}
	if IsMock() {
		decision["mock"] = true
		if len(serial) > 0 && decision["action"] == "TAP" && decision["target"] == "NONE" {
			decision["target"] = serial[0][0]
		}
	}
	return decision, usage, nil
}

// AskDecisionOpts opciones de AskDecision.
type AskDecisionOpts struct {
	HistorySummary string
	S2Guidance     string
	CurrentApp     string
	ScreenGoal     string
	FocusedField   map[string]any
	FirstResult    any
}

var _ = errors.New
