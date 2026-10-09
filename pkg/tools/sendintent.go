package tools

import "strings"

// Espejo de NatPolicies.canonicalizeAction/isCritical (Kotlin) para
// send_intent: misma canonicalización estricta antes del frame WS.
// Sin I/O, sin red: entra action cruda, sale forma canónica.

var criticalActions = map[string]bool{
	"android.intent.action.SEND":          true,
	"android.intent.action.SENDTO":        true,
	"android.intent.action.SEND_MULTIPLE": true,
	"android.intent.action.CALL":          true,
}

var sendSchemes = map[string]bool{
	"sms": true, "smsto": true, "mms": true, "mmsto": true, "tel": true, "mailto": true,
}

// CanonicalizeIntentAction trim+uppercase; SEND/ACTION_SEND/ACTION.SEND/
// action.send/.SEND y forma completa con/sin prefijo android.intent. →
// android.intent.action.SEND. Igual CALL, VIEW, SENDTO, SEND_MULTIPLE,
// DIAL. Desconocidas: trim sin inventar.
func CanonicalizeIntentAction(raw string) string {
	t := strings.ToUpper(strings.TrimSpace(raw))
	if t == "" {
		return ""
	}
	core := t
	// Prefijo android.intent. opcional (cubre action.* y action_*).
	if strings.HasPrefix(core, "ANDROID.INTENT.") {
		core = strings.TrimPrefix(core, "ANDROID.INTENT.")
	}
	switch {
	case strings.HasPrefix(core, "ACTION_"):
		core = strings.TrimPrefix(core, "ACTION_")
	case strings.HasPrefix(core, "ACTION."):
		core = strings.TrimPrefix(core, "ACTION.")
	case strings.HasPrefix(core, "."):
		core = strings.TrimPrefix(core, ".")
	}
	switch core {
	case "SEND", "SENDTO", "SEND_MULTIPLE", "CALL", "VIEW", "DIAL":
		return "android.intent.action." + core
	default:
		return strings.TrimSpace(raw)
	}
}

// IsCriticalIntent true si la acción (cualquier forma) es envío crítico
// o VIEW sobre esquema de envío. Espejo de NatPolicies.isCritical.
func IsCriticalIntent(action, uri string) bool {
	a := CanonicalizeIntentAction(action)
	if criticalActions[a] {
		return true
	}
	scheme := strings.ToLower(strings.SplitN(uri, ":", 2)[0])
	if sendSchemes[scheme] && (a == "android.intent.action.VIEW" || criticalActions[a]) {
		return true
	}
	return false
}
