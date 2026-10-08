package cost

import (
	"fmt"
	"os"
	"strconv"
	"sync"
)

// CostTracker dual-tier S1 + S2 (equiv. cost_tracker.py + core/cost.py).
// Tarifas: S1 normativas con overrides en vivo; S2 solo vía env
// (defaults = placeholder ajustable contra factura, nunca verdad oficial).

const JevDefaultIn = 0.042
const JevDefaultOut = 0.0

// PLACEHOLDER verificable 2026-10-05, override por GLM_RATE_IN/OUT.
const GlmPlaceholderIn = 0.15
const GlmPlaceholderOut = 0.50

func envFloat(name string, def float64) float64 {
	if v := os.Getenv(name); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

// JevModelID modelo S1 (env JEV_MODEL).
func JevModelID() string {
	if m := os.Getenv("JEV_MODEL"); m != "" {
		return m
	}
	return "typesafe/jev-1.13"
}

// S2ModelID modelo S2 agnóstico (cadena §2.1:
// JAV_AI_MODEL → S2_MODEL → GLM_MODEL → default). Retrocompat: la cadena
// histórica sigue mandando si JAV_AI_MODEL está vacío.
func S2ModelID() string { return GlmModelID() }

// GlmModelID alias histórico de S2ModelID (nombre conservado aunque el
// modelo ya no sea GLM; spec §2). Resuelve la cadena completa en vivo.
func GlmModelID() string {
	if m := os.Getenv("JAV_AI_MODEL"); m != "" {
		return m
	}
	if m := os.Getenv("S2_MODEL"); m != "" {
		return m
	}
	if m := os.Getenv("GLM_MODEL"); m != "" {
		return m
	}
	return "z-ai/glm-5.3-flash"
}

// JevRates (in, out) USD por MTok, con overrides JEV_RATE_IN/OUT en vivo.
func JevRates() (float64, float64) {
	return envFloat("JEV_RATE_IN", JevDefaultIn), envFloat("JEV_RATE_OUT", JevDefaultOut)
}

// GlmRates (in, out) USD por MTok, SOLO vía env GLM_RATE_IN/OUT en vivo.
func GlmRates() (float64, float64) {
	return envFloat("GLM_RATE_IN", GlmPlaceholderIn), envFloat("GLM_RATE_OUT", GlmPlaceholderOut)
}

// S2Rates alias de GlmRates (solo OpenRouter).
func S2Rates() (float64, float64) { return GlmRates() }

// RatesFor tarifa vigente para model, resolviendo env en vivo.
func RatesFor(model string) (float64, float64) {
	if model == JevModelID() {
		return JevRates()
	}
	return GlmRates()
}

// ModelRate tarifa de un modelo en USD por millón de tokens.
type ModelRate struct {
	Model      string
	InPerMTok  float64
	OutPerMTok float64
}

// CostUSD calcula coste del paso.
func (r ModelRate) CostUSD(inTok, outTok int) float64 {
	return float64(inTok)/1e6*r.InPerMTok + float64(outTok)/1e6*r.OutPerMTok
}

// Rates foto a import-time (los overrides se resuelven en vivo en RatesFor/Track).
var Rates = map[string][2]float64{
	JevModelID(): {envFloat("JEV_RATE_IN", JevDefaultIn), envFloat("JEV_RATE_OUT", JevDefaultOut)},
	GlmModelID(): {envFloat("GLM_RATE_IN", GlmPlaceholderIn), envFloat("GLM_RATE_OUT", GlmPlaceholderOut)},
}

// Tracker acumula coste USD por corrida; cada llamada LLM pasa por Track.
type Tracker struct {
	mu      sync.Mutex
	RunID   string
	JevCost float64
	S2Cost  float64
	Steps   int
	Lines   []string
}

// NewTracker crea un tracker por corrida.
func NewTracker(runID string) *Tracker { return &Tracker{RunID: runID} }

// Track registra una llamada y devuelve su coste USD del paso.
// tier="s1" acumula en jev_cost; cualquier otro en s2_cost.
// provider_cost directo si el proveedor devolvió coste sin tokens.
func (t *Tracker) Track(model string, inTok, outTok int, step *int, tier string, providerCost *float64) float64 {
	var usd float64
	var source string
	if providerCost != nil && inTok == 0 && outTok == 0 {
		usd = *providerCost
		source = "provider"
	} else {
		rin, rout := RatesFor(model)
		usd = float64(inTok)/1e6*rin + float64(outTok)/1e6*rout
		source = "computed"
	}
	stepStr := "nil"
	t.mu.Lock()
	if tier == "s1" {
		t.JevCost += usd
	} else {
		t.S2Cost += usd
	}
	if step != nil {
		if *step > t.Steps {
			t.Steps = *step
		}
		stepStr = strconv.Itoa(*step)
	}
	line := fmt.Sprintf("[COST] provider=openrouter model=%s in=%d out=%d usd=%.6f step=%s run=%s src=%s",
		model, inTok, outTok, usd, stepStr, t.RunID, source)
	t.Lines = append(t.Lines, line)
	t.mu.Unlock()
	// A stderr, nunca a stdout (spec §3.2).
	fmt.Fprintln(os.Stderr, line)
	return usd
}

// TotalCostUSD acumulado S1+S2.
func (t *Tracker) TotalCostUSD() float64 {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.JevCost + t.S2Cost
}

// Summary resumen {jev_cost, s2_cost, total_cost, steps}.
func (t *Tracker) Summary() map[string]any {
	t.mu.Lock()
	defer t.mu.Unlock()
	return map[string]any{
		"jev_cost": t.JevCost, "s2_cost": t.S2Cost,
		"total_cost": t.JevCost + t.S2Cost, "steps": t.Steps,
	}
}
