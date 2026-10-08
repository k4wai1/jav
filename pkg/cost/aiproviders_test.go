package cost

import (
	"testing"
)

// Cadena §2.1: JAV_AI_MODEL → S2_MODEL → GLM_MODEL → default.
func TestS2ModelChainJavAI(t *testing.T) {
	t.Setenv("JAV_AI_MODEL", "proveedor/modelo-a")
	t.Setenv("S2_MODEL", "custom/model")
	t.Setenv("GLM_MODEL", "other/model")
	if S2ModelID() != "proveedor/modelo-a" {
		t.Fatalf("JAV_AI_MODEL debe ganar: %s", S2ModelID())
	}
	t.Setenv("JAV_AI_MODEL", "")
	if S2ModelID() != "custom/model" {
		t.Fatalf("vacío JAV_AI_MODEL → S2_MODEL: %s", S2ModelID())
	}
	t.Setenv("S2_MODEL", "")
	if S2ModelID() != "other/model" {
		t.Fatalf("vacío JAV_AI+S2 → GLM_MODEL: %s", S2ModelID())
	}
	t.Setenv("GLM_MODEL", "")
	if S2ModelID() != "z-ai/glm-5.3-flash" {
		t.Fatalf("todo vacío → default: %s", S2ModelID())
	}
}
