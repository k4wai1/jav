package tools

import (
	"reflect"
	"testing"
)

// v2.4.0 (Fase 4): el diagnóstico de `device_status` debe ser determinista
// y honesto: solo lista lo que está presente y en `false` (una clave
// ausente ≠ apagada, apps viejas sin ese cap).

func TestMissingCapsSortedAndOnlyFalse(t *testing.T) {
	caps := map[string]bool{
		"accessibility": false,
		"shizuku":       true,
		"usage_access":  false,
		"camera":        true,
	}
	got := missingCaps(caps)
	want := []string{"accessibility", "usage_access"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("missing_caps=%v, esperado %v", got, want)
	}
	if empty := missingCaps(map[string]bool{"shizuku": true}); len(empty) != 0 {
		t.Fatalf("sin caps apagados missing_caps debe ser vacío: %v", empty)
	}
}

func TestSetupHintsAccessibilityConShizuku(t *testing.T) {
	caps := map[string]bool{
		"accessibility":          false,
		"shizuku":                true,
		"usage_access":           true,
		"notification_listening": true,
	}
	hints := setupHints(caps)
	if len(hints) != 1 {
		t.Fatalf("hints=%v, esperado solo accessibility", hints)
	}
	h := hints[0]
	if h["cap"] != "accessibility" {
		t.Fatalf("cap=%v, esperado accessibility", h["cap"])
	}
	actions, _ := h["actions"].([]map[string]any)
	if len(actions) != 2 {
		t.Fatalf("actions=%v, esperado repair + settings", actions)
	}
	// 1) La reparación asistida solo se ofrece si Shizuku está vivo.
	if actions[0]["tool"] != "device_status" {
		t.Fatalf("primera action=%v, esperado device_status(repair_accessibility)",
			actions[0]["tool"])
	}
	args, _ := actions[0]["args"].(map[string]any)
	if rep, _ := args["repair_accessibility"].(bool); !rep {
		t.Fatalf("args=%v, esperado repair_accessibility:true", args)
	}
	// 2) Siempre el panel manual como salida.
	if actions[1]["tool"] != "send_intent" {
		t.Fatalf("segunda action=%v, esperado send_intent", actions[1]["tool"])
	}
	sargs, _ := actions[1]["args"].(map[string]any)
	if sargs["action"] != "android.settings.ACCESSIBILITY_SETTINGS" {
		t.Fatalf("action=%v, esperado ACCESSIBILITY_SETTINGS", sargs["action"])
	}
}

func TestSetupHintsAccessibilitySinShizuku(t *testing.T) {
	hints := setupHints(map[string]bool{
		"accessibility": false,
		"shizuku":       false,
	})
	// accessibility + shizuku = 2 hints; el de a11y NO ofrece reparación.
	if len(hints) != 2 {
		t.Fatalf("hints=%v, esperado accessibility + shizuku", hints)
	}
	a11y := hints[0]
	actions, _ := a11y["actions"].([]map[string]any)
	if len(actions) != 1 {
		t.Fatalf("actions=%v, sin Shizuku solo se ofrece el panel", actions)
	}
	if actions[0]["tool"] != "send_intent" {
		t.Fatalf("action=%v, esperado send_intent", actions[0]["tool"])
	}
	// Shizuku se arranca a mano: hint sin acciones ejecutables.
	sh := hints[1]
	if sh["cap"] != "shizuku" {
		t.Fatalf("segundo cap=%v, esperado shizuku", sh["cap"])
	}
	if acts, _ := sh["actions"].([]map[string]any); len(acts) != 0 {
		t.Fatalf("shizuku no debe traer acciones: %v", acts)
	}
}

func TestSetupHintsUsageYNotificaciones(t *testing.T) {
	hints := setupHints(map[string]bool{
		"accessibility":          true,
		"shizuku":                true,
		"usage_access":           false,
		"notification_listening": false,
	})
	if len(hints) != 2 {
		t.Fatalf("hints=%v, esperado usage_access + notification_listening", hints)
	}
	want := map[string]string{
		"usage_access":           "android.settings.USAGE_ACCESS_SETTINGS",
		"notification_listening": "android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS",
	}
	for _, h := range hints {
		capName, _ := h["cap"].(string)
		actions, _ := h["actions"].([]map[string]any)
		if len(actions) != 1 {
			t.Fatalf("%s: actions=%v, esperado 1", capName, actions)
		}
		args, _ := actions[0]["args"].(map[string]any)
		if args["action"] != want[capName] {
			t.Fatalf("%s: action=%v, esperado %v", capName, args["action"], want[capName])
		}
	}
}

func TestSetupHintsNoInventaCapsAusentes(t *testing.T) {
	// Hello sin caps (app <1.2.5): el mapa vacío NO debe fabricar hints.
	if hints := setupHints(map[string]bool{}); len(hints) != 0 {
		t.Fatalf("mapa vacío no debe generar hints: %v", hints)
	}
	// Solo claves presentes en false generan hint.
	if hints := setupHints(map[string]bool{"camera": false}); len(hints) != 0 {
		t.Fatalf("caps no cubiertos no generan hint: %v", hints)
	}
}
