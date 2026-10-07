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
