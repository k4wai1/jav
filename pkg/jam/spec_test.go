package jam

import (
	"strings"
	"testing"
)

// Guía §3.2: todo código de la tabla (y cualquier futuro) sale con
// recovery_instruction imperativa, nunca vacía.

var tableCodes = []string{
	"STALE_SNAPSHOT", "NOT_FOCUSED", "SELECTOR_NOT_FOUND", "TIMEOUT",
	"ACCESSIBILITY_DISABLED", "SHIZUKU_UNAVAILABLE", "SHIZUKU_DENIED",
	"UNAUTHORIZED", "FORBIDDEN", "METHOD_NOT_ALLOWED", "VALIDATION_ERROR",
	"SECURE_SURFACE", "PAYLOAD_TOO_LARGE", "INTENT_UNRESOLVED",
	"PACKAGE_NOT_FOUND", "CLIPBOARD_EMPTY", "UI_UNSTABLE", "VERIFY_FAILED",
	"CONNECTION_FAILED", "RATE_LIMITED", "BUSY", "SHELL_DENIED",
	"SHELL_DENYLIST", "USAGE_ACCESS_DISABLED", "CONTACTS_PERMISSION_DENIED",
	"CALENDAR_PERMISSION_DENIED", "NOTIFICATION_LISTENER_DISABLED",
	"MEDIA_SESSIONS_UNAVAILABLE", "LOCATION_PERMISSION_DENIED",
	"CAMERA_DENIED", "WRITE_SETTINGS_DISABLED", "NOTIFICATION_GONE",
	"NO_REMOTE_INPUT", "REPLY_FAILED", "MEDIA_SESSION_GONE",
	"MEDIA_CONTROL_FAILED", "LOCATION_UNAVAILABLE", "LOCATION_TIMEOUT",
	"CAMERA_UNAVAILABLE", "CAMERA_FAILED", "SETTINGS_PUT_FAILED",
	"CALENDAR_UNAVAILABLE", "INTENT_FAILED",
}

func TestHintForWholeTable(t *testing.T) {
	for _, code := range tableCodes {
		h := hintFor(code)
		if strings.TrimSpace(h) == "" {
			t.Fatalf("%s: hint vacío (prohibido por §3.1)", code)
		}
	}
}

func TestHintForUnknownCodeFallsBack(t *testing.T) {
	if h := hintFor("FUTURE_CODE_X"); strings.TrimSpace(h) == "" {
		t.Fatalf("código desconocido debe traer hint genérico, no vacío")
	}
}

func TestJamFailEnvelope(t *testing.T) {
	env := JamFail(&JamError{Code: "STALE_SNAPSHOT", Message: "rotó"})
	if ok, _ := env["ok"].(bool); ok {
		t.Fatalf("fail debe ser ok:false")
	}
	ev, _ := env["evidence"].(map[string]any)
	if ev["code"] != "STALE_SNAPSHOT" {
		t.Fatalf("code: %v", ev)
	}
	if strings.TrimSpace(env["hint"].(string)) == "" {
		t.Fatalf("hint vacío")
	}
}

// Núcleo canónico intacto (compatibilidad forense): verbatim histórico.
func TestHintCoreUnchanged(t *testing.T) {
	core := map[string]string{
		"STALE_SNAPSHOT":         "re-haz read_screen y usa el snapshot nuevo",
		"NOT_FOCUSED":            "haz tap sobre el campo antes de type_text",
		"SELECTOR_NOT_FOUND":     "re-haz read_screen; el selector no matchea",
		"ACCESSIBILITY_DISABLED": "habilita Jam en Ajustes → Accesibilidad",
		"SHIZUKU_UNAVAILABLE":    "arranca Shizuku y reintenta",
		"TIMEOUT":                "reintenta o sube el timeout",
		"SECURE_SURFACE":         "la ventana tiene FLAG_SECURE; usa dump_ui, no screenshot",
		"PAYLOAD_TOO_LARGE":      "reintenta con fmt webp y quality 80",
		"METHOD_NOT_ALLOWED":     "metodo no disponible en esta fase; no reintentes igual",
		"UNAUTHORIZED":           "revisa JAV_TOKEN en el entorno del servidor",
	}
	for code, want := range core {
		if hintFor(code) != want {
			t.Fatalf("%s: cambió el núcleo: %q", code, hintFor(code))
		}
	}
}
