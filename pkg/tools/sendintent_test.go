package tools

import "testing"

func TestCanonicalizeIntentAction(t *testing.T) {
	cases := map[string]string{
		"SEND": "android.intent.action.SEND", "ACTION_SEND": "android.intent.action.SEND",
		".SEND": "android.intent.action.SEND", "action.send": "android.intent.action.SEND",
		"ACTION.SEND": "android.intent.action.SEND",
		"android.intent.action.SEND": "android.intent.action.SEND",
		"android.intent.ACTION.SEND": "android.intent.action.SEND",
		"android.intent.SEND":        "android.intent.action.SEND",
		"  send  ": "android.intent.action.SEND", "android.intent.action.send": "android.intent.action.SEND",
		"CALL": "android.intent.action.CALL", "ACTION_CALL": "android.intent.action.CALL",
		".CALL": "android.intent.action.CALL", "action.call": "android.intent.action.CALL",
		"ACTION.CALL": "android.intent.action.CALL", "android.intent.CALL": "android.intent.action.CALL",
		" android.intent.action.call ": "android.intent.action.CALL",
		"VIEW": "android.intent.action.VIEW", "ACTION_VIEW": "android.intent.action.VIEW",
		"ACTION.VIEW": "android.intent.action.VIEW", "action.view": "android.intent.action.VIEW",
		".VIEW": "android.intent.action.VIEW",
		"android.intent.action.VIEW": "android.intent.action.VIEW",
		"sendto": "android.intent.action.SENDTO",
		"ACTION_SEND_MULTIPLE": "android.intent.action.SEND_MULTIPLE",
		"ACTION.SEND_MULTIPLE": "android.intent.action.SEND_MULTIPLE",
		"dial": "android.intent.action.DIAL",
	}
	for in, want := range cases {
		if got := CanonicalizeIntentAction(in); got != want {
			t.Fatalf("canonicalize %q = %q, want %q", in, got, want)
		}
	}
	if got := CanonicalizeIntentAction("  com.ejemplo.CUSTOM "); got != "com.ejemplo.CUSTOM" {
		t.Fatalf("desconocida debe hacer trim sin inventar: %q", got)
	}
	if got := CanonicalizeIntentAction("   "); got != "" {
		t.Fatalf("vacía debe ser \"\": %q", got)
	}
}

func TestIsCriticalIntentShortForms(t *testing.T) {
	for _, a := range []string{"SEND", "ACTION_SEND", "action_send", ".SEND", "action.send", "ACTION.SEND", "android.intent.action.SEND", "android.intent.SEND"} {
		if !IsCriticalIntent(a, "") {
			t.Fatalf("%q debe ser crítico", a)
		}
	}
	for _, a := range []string{"CALL", "ACTION_CALL", ".CALL", "action.call", "ACTION.CALL", " call ", "android.intent.CALL"} {
		if !IsCriticalIntent(a, "tel:123") {
			t.Fatalf("%q debe ser crítico", a)
		}
	}
	if !IsCriticalIntent("VIEW", "sms:123?body=hola") {
		t.Fatalf("VIEW a sms debe ser crítico")
	}
	if !IsCriticalIntent("ACTION.VIEW", "sms:123?body=hola") {
		t.Fatalf("ACTION.VIEW a sms debe ser crítico")
	}
	if IsCriticalIntent("VIEW", "https://x.test/a") {
		t.Fatalf("VIEW https no debe ser crítico")
	}
	if IsCriticalIntent("ACTION.VIEW", "https://x.test/a") {
		t.Fatalf("ACTION.VIEW https no debe ser crítico (VIEW libre)")
	}
	if IsCriticalIntent("action.view", "https://x.test/a") {
		t.Fatalf("action.view https no debe ser crítico (VIEW libre)")
	}
	if IsCriticalIntent("DIAL", "tel:123") {
		t.Fatalf("DIAL no debe ser crítico")
	}
}
