package cost

import (
	"os"
	"testing"
)

func TestTrackJevNormative(t *testing.T) {
	os.Unsetenv("JEV_RATE_IN")
	os.Unsetenv("JEV_RATE_OUT")
	tr := NewTracker("run-test")
	usd := tr.Track("typesafe/jev-1.13", 1_000_000, 500_000, nil, "s1", nil)
	if usd != 0.042 {
		t.Fatalf("S1 1MTok in debe ser 0.042 (out 0.0): %f", usd)
	}
	if tr.JevCost != 0.042 || tr.TotalCostUSD() != 0.042 {
		t.Fatalf("acumulado: %+v", tr.Summary())
	}
}

func TestTrackProviderCost(t *testing.T) {
	tr := NewTracker("r")
	pc := 0.001
	usd := tr.Track("z-ai/glm-5.3-flash", 0, 0, nil, "s2", &pc)
	if usd != pc || tr.S2Cost != pc {
		t.Fatalf("provider_cost directo: %f", usd)
	}
}

func TestStubZero(t *testing.T) {
	tr := NewTracker("r")
	if usd := tr.Track("m", 0, 0, nil, "s1", nil); usd != 0.0 {
		t.Fatalf("stub debe ser 0.0: %f", usd)
	}
}

func TestS2ModelPrecedence(t *testing.T) {
	os.Setenv("S2_MODEL", "custom/model")
	defer os.Unsetenv("S2_MODEL")
	os.Setenv("GLM_MODEL", "other/model")
	defer os.Unsetenv("GLM_MODEL")
	if S2ModelID() != "custom/model" {
		t.Fatalf("S2_MODEL manda sobre GLM_MODEL: %s", S2ModelID())
	}
}

// v1.2.0: acumulador global de sesión (evidencia.cost), sin depender de stderr.
func TestSessionSummaryAccumulates(t *testing.T) {
	ResetSession()
	tr := NewTracker("r-session")
	_ = tr.Track("typesafe/jev-1.13", 1_000_000, 0, nil, "s1", nil)
	pc := 0.5
	_ = tr.Track("z-ai/glm-5.3-flash", 0, 0, nil, "s2", &pc)
	s := SessionSummary()
	if s["calls"].(int) != 2 {
		t.Fatalf("calls: %v", s)
	}
	if s["jev_cost_usd"].(float64) != 0.042 || s["s2_cost_usd"].(float64) != 0.5 {
		t.Fatalf("costes por tier: %v", s)
	}
	if s["total_cost_usd"].(float64) != 0.542 {
		t.Fatalf("total: %v", s)
	}
	ResetSession()
	if SessionSummary()["calls"].(int) != 0 {
		t.Fatalf("ResetSession debe limpiar")
	}
}

// Track es silencioso por defecto (el resumen va en evidence.cost); con
// JAV_DEBUG_COST=1 sigue acumulando igual.
func TestTrackSilentByDefault(t *testing.T) {
	os.Unsetenv("JAV_DEBUG_COST")
	ResetSession()
	tr := NewTracker("r-silent")
	if usd := tr.Track("typesafe/jev-1.13", 1_000_000, 0, nil, "s1", nil); usd != 0.042 {
		t.Fatalf("usd: %f", usd)
	}
	if SessionSummary()["calls"].(int) != 1 {
		t.Fatalf("debe acumular aunque no imprima")
	}
}
