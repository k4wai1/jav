package tools

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"
)

// Handlers native/ (equiv. tools/native.py): carril APIs directas.
// Cada llamada pasa por _jamCall con latency_ms; PII solo conteos/hashes.

func forenseSummary(canonical string, count int) map[string]any {
	sum := sha256.Sum256([]byte(canonical))
	return map[string]any{"count": count, "sha256": hex.EncodeToString(sum[:])}
}

func hGetBattery(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	return result(jamCallLatency("get_battery", map[string]any{}))
}

func hGetMemory(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	return result(jamCallLatency("get_memory", map[string]any{}))
}

func hGetStorage(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	detail := getString(args, "detail", "basic")
	if bad := checkDetail(detail); bad != nil {
		return result(*bad)
	}
	return result(jamCallLatency("get_storage", map[string]any{"detail": detail}))
}

func hGetCPU(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	detail := getString(args, "detail", "basic")
	if bad := checkDetail(detail); bad != nil {
		return result(*bad)
	}
	return result(jamCallLatency("get_cpu", map[string]any{"detail": detail}))
}

func hGetDeviceInfo(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	return result(jamCallLatency("get_device_info", map[string]any{}))
}

func hSettingsGet(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	ns := getString(args, "namespace", "system")
	key := getString(args, "key", "")
	if bad := checkNamespace(ns); bad != nil {
		return result(*bad)
	}
	if key == "" {
		return result(validationError("key vacía"))
	}
	return result(jamCallLatency("settings_get", map[string]any{"namespace": ns, "key": key}))
}

func hSettingsPut(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	ns := getString(args, "namespace", "system")
	key := getString(args, "key", "")
	value := getString(args, "value", "")
	confirm := getBool(args, "confirm", false)
	if bad := checkNamespace(ns); bad != nil {
		return result(*bad)
	}
	if key == "" {
		return result(validationError("key vacía"))
	}
	return result(jamCallLatency("settings_put", map[string]any{
		"namespace": ns, "key": key, "value": value, "confirm": confirm,
	}))
}

func hOpenURL(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	url := getString(args, "url", "")
	pkg := getString(args, "package", "")
	if url == "" {
		return result(validationError("url vacía"))
	}
	if bad := checkURL(url); bad != nil {
		return result(*bad)
	}
	if pkg != "" {
		if bad := checkPackage(pkg); bad != nil {
			return result(*bad)
		}
	}
	return result(jamCallLatency("open_url", map[string]any{"url": url, "package": pkg}))
}

func hSendIntent(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	action := getString(args, "action", "")
	uri := getString(args, "uri", "")
	pkg := getString(args, "package", "")
	mime := getString(args, "mime", "")
	confirm := getBool(args, "confirm", false)
	if action == "" {
		return result(validationError("action vacía"))
	}
	if pkg != "" {
		if bad := checkPackage(pkg); bad != nil {
			return result(*bad)
		}
	}
	extras := map[string]any{}
	if e, ok := args["extras"].(map[string]any); ok {
		extras = e
	}
	return result(jamCallLatency("send_intent", map[string]any{
		"action": action, "uri": uri, "package": pkg, "mime": mime,
		"confirm": confirm, "extras": extras,
	}))
}

func hGetClipboardDevice(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	env := jamCallLatency("get_clipboard", map[string]any{})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		length, _ := ev["len"].(float64)
		sha, _ := ev["sha256"].(string)
		ev["forense"] = map[string]any{"via": "jam-foreground", "len": length, "sha256": sha}
	}
	return result(env)
}

func hGetAppUsage(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	hours := getInt(args, "hours", 24)
	window := getNullableString(args, "window")
	if bad := checkWindow(window); bad != nil {
		return result(*bad)
	}
	maxH := 24
	if window == "raw" {
		maxH = 168
	}
	if hours < 1 || hours > maxH {
		return result(validationError("hours fuera de rango"))
	}
	var w any
	if hasKey(args, "window") {
		if s, ok := args["window"].(string); ok {
			w = s
		}
	}
	return result(jamCallLatency("get_app_usage", map[string]any{"hours": hours, "window": w}))
}

func hListContacts(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	query := getString(args, "query", "")
	limit := getInt(args, "limit", 50)
	offset := getInt(args, "offset", 0)
	withPhone := getBool(args, "with_phone", false)
	if limit < 1 || limit > 100 {
		return result(validationError("limit fuera de 1..100"))
	}
	if offset < 0 {
		return result(validationError("offset negativo"))
	}
	env := jamCallLatency("list_contacts", map[string]any{
		"query": query, "limit": limit, "offset": offset, "with_phone": withPhone,
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		var canon string
		if cs, ok := ev["contacts"].([]any); ok {
			for _, item := range cs {
				if c, ok := item.(map[string]any); ok {
					canon += sprintJSON(c["id"]) + "|"
				}
			}
		}
		count := 0
		if cs, ok := ev["contacts"].([]any); ok {
			count = len(cs)
		}
		ev["forense"] = forenseSummary(canon, count)
	}
	return result(env)
}

func hAddContact(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	name := getString(args, "display_name", "")
	phone := getString(args, "phone", "")
	email := getString(args, "email", "")
	confirm := getBool(args, "confirm", false)
	if name == "" {
		return result(validationError("display_name vacío"))
	}
	return result(jamCallLatency("add_contact", map[string]any{
		"display_name": name, "phone": phone, "email": email, "confirm": confirm,
	}))
}

func hListEvents(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	tMin := getInt64(args, "time_min", 0)
	tMax := getInt64(args, "time_max", 0)
	calID := getInt(args, "calendar_id", 0)
	inclLoc := getBool(args, "include_location", false)
	const weekMs = int64(7 * 24 * 3600 * 1000)
	effMax := tMax
	effMin := tMin
	if effMax == 0 {
		effMax = effMin + weekMs
	}
	if effMax-effMin > weekMs {
		return result(validationError("ventana mayor a 7 días"))
	}
	env := jamCallLatency("list_events", map[string]any{
		"time_min": tMin, "time_max": tMax, "calendar_id": calID,
		"include_location": inclLoc,
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		var canon string
		count := 0
		if es, ok := ev["events"].([]any); ok {
			count = len(es)
			for _, item := range es {
				if e, ok := item.(map[string]any); ok {
					canon += sprintJSON(e["event_id"]) + ":" + sprintJSON(e["begin"]) + "|"
				}
			}
		}
		ev["forense"] = forenseSummary(canon, count)
	}
	return result(env)
}

func hCreateEvent(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	title := getString(args, "title", "")
	startMs := getInt64(args, "start_ms", 0)
	endMs := getInt64(args, "end_ms", 0)
	calID := getInt(args, "calendar_id", 0)
	desc := getString(args, "description", "")
	confirm := getBool(args, "confirm", false)
	if title == "" {
		return result(validationError("title vacío"))
	}
	if endMs <= startMs {
		return result(validationError("end_ms debe ser > start_ms"))
	}
	return result(jamCallLatency("create_event", map[string]any{
		"calendar_id": calID, "title": title, "start_ms": startMs,
		"end_ms": endMs, "description": desc, "confirm": confirm,
	}))
}

func hListNotifications(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	env := jamCallLatency("list_notifications", map[string]any{})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		var canon string
		count := 0
		if ns, ok := ev["notifications"].([]any); ok {
			count = len(ns)
			for _, item := range ns {
				if n, ok := item.(map[string]any); ok {
					canon += sprintJSON(n["key"]) + "|"
				}
			}
		}
		ev["forense"] = forenseSummary(canon, count)
	}
	return result(env)
}

func hReplyNotification(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	key := getString(args, "key", "")
	text := getString(args, "text", "")
	confirm := getBool(args, "confirm", false)
	if key == "" || text == "" {
		return result(validationError("key/text vacíos"))
	}
	return result(jamCallLatency("reply_notification", map[string]any{
		"key": key, "text": text, "confirm": confirm,
	}))
}

func hMediaState(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	return result(jamCallLatency("media_state", map[string]any{}))
}

func hMediaControl(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	action := getString(args, "action", "")
	pkg := getString(args, "package", "")
	confirm := getBool(args, "confirm", false)
	if bad := checkMediaAction(action); bad != nil {
		return result(*bad)
	}
	return result(jamCallLatency("media_control", map[string]any{
		"action": action, "package": pkg, "confirm": confirm,
	}))
}

func hGetLocation(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	timeoutMs := getInt(args, "timeout_ms", 8000)
	maxAgeS := getInt(args, "max_age_s", 300)
	if timeoutMs < 0 || timeoutMs > 30000 {
		return result(validationError("timeout_ms fuera de rango (≤30000)"))
	}
	if maxAgeS < 0 || maxAgeS > 3600 {
		return result(validationError("max_age_s fuera de rango (≤3600)"))
	}
	env := jamCallLatency("get_location", map[string]any{
		"timeout_ms": timeoutMs, "max_age_s": maxAgeS,
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		canon := sprintJSON(ev["lat"]) + "," + sprintJSON(ev["lon"]) + "," + sprintJSON(ev["accuracy_m"])
		sum := sha256.Sum256([]byte(canon))
		via, _ := ev["via"].(string)
		ev["forense"] = map[string]any{"via": via, "sha256": hex.EncodeToString(sum[:])}
	}
	return result(env)
}

func hTakePhoto(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	confirm := getBool(args, "confirm", false)
	camera := getString(args, "camera", "back")
	if bad := checkCamera(camera); bad != nil {
		return result(*bad)
	}
	return result(jamCallLatency("take_photo", map[string]any{
		"confirm": confirm, "camera": camera,
	}))
}

func sprintJSON(v any) string {
	if v == nil {
		return ""
	}
	switch t := v.(type) {
	case string:
		return t
	case float64:
		return itoaFloat(t)
	case bool:
		if t {
			return "true"
		}
		return "false"
	default:
		return ""
	}
}

func itoaFloat(f float64) string {
	if f == float64(int64(f)) {
		return itoaInt(int64(f))
	}
	return dtoa(f)
}

func itoaInt(n int64) string {
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	if n == 0 {
		i--
		buf[i] = '0'
	}
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

func dtoa(f float64) string {
	return strings.TrimRight(strings.TrimRight(floatToString(f), "0"), ".")
}

func floatToString(f float64) string {
	// Formato simple sin exponentes para magnitudes normales.
	s := ""
	neg := f < 0
	if neg {
		f = -f
		s = "-"
	}
	ip := int64(f)
	frac := f - float64(ip)
	s += itoaInt(ip) + "."
	for i := 0; i < 6; i++ {
		frac *= 10
		d := int(frac)
		s += string(rune('0' + d))
		frac -= float64(d)
	}
	return s
}
