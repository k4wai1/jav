package tools

import (
	"strings"
	"testing"

	"github.com/mark3labs/mcp-go/server"
)

// Guía §2: las 38 tools llevan §6 (Cuándo NO + alternativa exacta) y
// §7 (Ejemplo genérico). Sin literales de dominio. El contrato cognitivo
// completo vive en FullToolDocs (catalog.go) y viaja bajo demanda por
// Resource; la verificación recorre el mapa completo (38 fichas).

var affordNeedles = []string{
	"Descripcion:", "Parametros:", "Retorno:",
	"Permisos/Grants:", "Errores/gotchas:",
	"Cuándo NO usar", "Ejemplo", "→",
}

func TestAllDescriptionsHaveSections6And7(t *testing.T) {
	if len(FullToolDocs) != 38 {
		t.Fatalf("se esperan 38 fichas completas, hay %d", len(FullToolDocs))
	}
	for name, d := range FullToolDocs {
		for _, n := range affordNeedles {
			if !strings.Contains(d, n) {
				t.Fatalf("%s sin %q", name, n)
			}
		}
	}
}

func TestCompactDescriptions(t *testing.T) {
	if len(toolDefs) != 38 {
		t.Fatalf("38 tools, hay %d", len(toolDefs))
	}
	for _, d := range toolDefs {
		c := CompactDesc(d.name)
		if !strings.HasPrefix(c, "["+GroupOf(d.name)+"]") {
			t.Fatalf("%s sin prefijo [grupo]: %q", d.name, c)
		}
		for _, n := range []string{"Retorno:", "{ok", "verified", "evidence", "hint",
			"Spec: android://tool/" + d.name} {
			if !strings.Contains(c, n) {
				t.Fatalf("%s compacta sin %q", d.name, n)
			}
		}
		if SensitiveTools[d.name] {
			for _, n := range []string{"planned:true", "preview", "confirm"} {
				if !strings.Contains(c, n) {
					t.Fatalf("%s sensible compacta sin %q", d.name, n)
				}
			}
		}
	}
}

func TestDescriptionsWithoutDomainLiterals(t *testing.T) {
	for name, d := range FullToolDocs {
		low := strings.ToLower(d)
		// `OPENROUTER_API_KEY` es un identificador de entorno legítimo (no un
		// nombre de app ni un secreto embebido): se neutraliza antes de barrer.
		low = strings.ReplaceAll(low, "openrouter_api_key", "")
		for _, lit := range []string{"whatsapp", "contact_name", "verify_chat",
			"wrong_chat", "api_key", "gmail", "telegram"} {
			if strings.Contains(low, lit) {
				t.Fatalf("%s con literal de dominio %q", name, lit)
			}
		}
	}
}

func TestValidationErrorHint(t *testing.T) {
	env := validationError("direction inválida")
	if ok, _ := env["ok"].(bool); ok {
		t.Fatalf("validation debe ser ok:false")
	}
	ev, _ := env["evidence"].(map[string]any)
	if ev["code"] != "VALIDATION_ERROR" {
		t.Fatalf("code: %v", ev)
	}
	h, _ := env["hint"].(string)
	if !strings.Contains(h, "unidades") || strings.TrimSpace(h) == "" {
		t.Fatalf("hint VALIDATION_ERROR debe citar forma/enum/rangos/unidades: %q", h)
	}
}

func TestPromptBodiesCarryGates(t *testing.T) {
	for name, wants := range map[string][]string{
		"troubleshoot_app":  {"read_screen", "STALE_SNAPSHOT", "hint"},
		"navigate_and_copy": {"planned:true", "confirm:true", "CLIPBOARD_EMPTY"},
		"send_verified":     {"planned:true", "confirm:true", "read_screen"},
	} {
		var body string
		switch name {
		case "troubleshoot_app":
			body = promptTroubleshoot
		case "navigate_and_copy":
			body = promptNavigateAndCopy
		default:
			body = promptSendVerified
		}
		for _, want := range wants {
			if !strings.Contains(body, want) {
				t.Fatalf("%s sin %q", name, want)
			}
		}
		if strings.Contains(strings.ToLower(body), "shell") {
			t.Fatalf("%s expone shell", name)
		}
	}
}

func TestRegisterExtrasDoesNotPanic(t *testing.T) {
	s := server.NewMCPServer("jav-test", "0.0.0")
	RegisterExtras(s)
}
