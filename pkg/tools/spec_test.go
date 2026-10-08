package tools

import (
	"strings"
	"testing"

	"github.com/mark3labs/mcp-go/server"
)

// Guía §2: las 35 tools llevan §6 (Cuándo NO + alternativa exacta) y
// §7 (Ejemplo genérico). Sin literales de dominio.

var allDescs = []string{
	dDeviceStatus, dListPackages, dGetForeground, dOpenApp, dCloseApp,
	dReadScreen, dTapText, dTapNode, dTypeText, dScroll, dPressBack,
	dPressHome, dWaitForText, dScreenshot, dGetBattery, dGetMemory,
	dGetStorage, dGetCPU, dGetDeviceInfo, dSettingsGet, dSettingsPut,
	dOpenURL, dSendIntent, dGetClipboardDevice, dGetAppUsage,
	dListContacts, dAddContact, dListEvents, dCreateEvent,
	dListNotifications, dReplyNotification, dMediaState, dMediaControl,
	dGetLocation, dTakePhoto,
}

func TestAllDescriptionsHaveSections6And7(t *testing.T) {
	if len(allDescs) != 35 {
		t.Fatalf("se esperan 35 descripciones, hay %d", len(allDescs))
	}
	for i, d := range allDescs {
		if !strings.Contains(d, "Cuándo NO usar") {
			t.Fatalf("desc %d sin §6", i)
		}
		if !strings.Contains(d, "Ejemplo") {
			t.Fatalf("desc %d sin §7", i)
		}
		if !strings.Contains(d, "→") {
			t.Fatalf("desc %d sin alternativa (→)", i)
		}
	}
}

func TestDescriptionsWithoutDomainLiterals(t *testing.T) {
	for i, d := range allDescs {
		low := strings.ToLower(d)
		for _, lit := range []string{"whatsapp", "contact_name", "verify_chat",
			"wrong_chat", "api_key", "gmail", "telegram"} {
			if strings.Contains(low, lit) {
				t.Fatalf("desc %d con literal de dominio %q", i, lit)
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
		"troubleshoot_app": {"read_screen", "STALE_SNAPSHOT", "hint"},
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
