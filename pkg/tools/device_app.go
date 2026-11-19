package tools

import (
	"context"
	"os/exec"
	"sort"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/jam"
)

// Handlers device/ + app/ (equiv. tools/device.py + tools/app.py).

func hDeviceStatus(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	// v2.2.0: cambio de dispositivo en caliente antes de conectar.
	if sel := strings.TrimSpace(getString(args, "select_device", "")); sel != "" {
		if _, err := jam.SelectDevice(sel); err != nil {
			return result(jam.Fail("VALIDATION_ERROR", err.Error(),
				"usa un alias de paired_devices o vincula con jav pair --name <alias> <ip> <token>"))
		}
	}
	c, jerr := jam.Dial()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	defer c.Close()

	evidence := map[string]any{}

	// v2.4.0 (Fase 4): reparación asistida de accesibilidad ANTES de leer
	// caps. Un fallo NO aborta el diagnóstico: se reporta en `repair` para
	// que el agente vea el estado completo (p. ej. SHIZUKU_UNAVAILABLE).
	if getBool(args, "repair_accessibility", false) {
		if rep, rerr := c.EnableAccessibility(); rerr != nil {
			evidence["repair"] = map[string]any{
				"ok": false, "code": rerr.Code, "error": rerr.Message,
			}
		} else {
			m := map[string]any{"ok": true}
			for k, v := range rep {
				m[k] = v
			}
			evidence["repair"] = m
		}
	}

	// Caps VIVOS vía `get_caps` (v2.4.0): no exige accesibilidad, justo el
	// estado que hay que diagnosticar. APK <2.4.0 (METHOD_NOT_ALLOWED) o
	// fallo de red → caps del hello (no se inventa nada).
	caps := c.Caps
	if live, capsErr := c.GetCaps(); capsErr == nil {
		caps = live
	} else if capsErr.Code != "METHOD_NOT_ALLOWED" {
		// Degradación visible: seguimos con los caps del hello, pero el
		// agente ve por qué no son vivos (nunca se oculta el fallo).
		evidence["caps_error"] = capsErr.Code
	}
	if caps == nil {
		caps = map[string]bool{}
	}

	// Foreground es O(1) pero exige el servicio de accesibilidad. Si está
	// apagado, `device_status` degrada honesto (ok:true, verified:false)
	// en vez de abortar: caps, missing_caps y setup_hints siguen siendo
	// útiles para repararlo.
	verified := true
	fg, ferr := c.GetForeground()
	var foreground any = fg
	if ferr != nil {
		if ferr.Code != "ACCESSIBILITY_DISABLED" {
			return result(jam.JamFail(ferr))
		}
		foreground = nil
		evidence["foreground_error"] = "ACCESSIBILITY_DISABLED"
		verified = false
	} else {
		// Compat v2.3.1: apps <2.4.0 no tienen `get_caps`; el foreground
		// sigue siendo la fuente de caps vivos.
		if live, ok := fg["caps"].(map[string]any); ok {
			for k, v := range live {
				if b, ok := v.(bool); ok {
					caps[k] = b
				}
			}
		}
	}

	evidence["scopes"] = c.Scopes
	evidence["app_version"] = c.AppVersion
	evidence["foreground"] = foreground
	evidence["caps"] = caps
	evidence["missing_caps"] = missingCaps(caps)
	evidence["setup_hints"] = setupHints(caps)
	evidence["cost"] = cost.SessionSummary()
	evidence["active_device"] = jam.ActiveDeviceName()
	evidence["paired_devices"] = jam.PairedDeviceNames()
	return result(jam.OK(verified, evidence, ""))
}

// missingCaps lista las claves presentes en `caps` con valor `false`,
// ordenadas alfabéticamente (diagnóstico estable entre llamadas). Las
// claves ausentes NO se inventan (apps viejas sin ese cap).
func missingCaps(caps map[string]bool) []string {
	out := make([]string, 0, len(caps))
	for k, v := range caps {
		if !v {
			out = append(out, k)
		}
	}
	sort.Strings(out)
	return out
}

// setupHints traduce cada permiso apagado a acciones concretas (Fase 4:
// preconfiguración asistida). Solo emite hints para caps PRESENTES en el
// mapa: ausente ≠ apagado. `shizuku` no trae acción ejecutable porque Jav
// nunca arranca Shizuku (lo arranca el operador, AGENTS.md §2).
func setupHints(caps map[string]bool) []map[string]any {
	hints := make([]map[string]any, 0, 4)
	if v, ok := caps["accessibility"]; ok && !v {
		actions := []map[string]any{}
		if caps["shizuku"] {
			actions = append(actions, map[string]any{
				"tool": "device_status",
				"args": map[string]any{"repair_accessibility": true},
			})
		}
		actions = append(actions, map[string]any{
			"tool": "send_intent",
			"args": map[string]any{
				"action": "android.settings.ACCESSIBILITY_SETTINGS",
			},
		})
		hints = append(hints, map[string]any{
			"cap":     "accessibility",
			"hint":    "habilita el servicio de accesibilidad de Jav",
			"actions": actions,
		})
	}
	if v, ok := caps["usage_access"]; ok && !v {
		hints = append(hints, map[string]any{
			"cap":  "usage_access",
			"hint": "concede «Acceso a datos de uso»",
			"actions": []map[string]any{{
				"tool": "send_intent",
				"args": map[string]any{
					"action": "android.settings.USAGE_ACCESS_SETTINGS",
				},
			}},
		})
	}
	if v, ok := caps["notification_listening"]; ok && !v {
		hints = append(hints, map[string]any{
			"cap":  "notification_listening",
			"hint": "habilita el Acceso a notificaciones",
			"actions": []map[string]any{{
				"tool": "send_intent",
				"args": map[string]any{
					"action": "android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS",
				},
			}},
		})
	}
	if v, ok := caps["shizuku"]; ok && !v {
		hints = append(hints, map[string]any{
			"cap":     "shizuku",
			"hint":    "Shizuku lo arranca el operador: ábrelo, arráncalo y reintenta (Jav nunca lo arranca)",
			"actions": []map[string]any{},
		})
	}
	return hints
}

func hListPackages(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	filter := getString(args, "filter", "")
	// v2.0.0: lista nativa por WebSocket (Termux/WSS sin USB). Solo cae a
	// `adb` si la APK es <2.0.0 (METHOD_NOT_ALLOWED) o no hay conexión.
	var jerr *jam.JamError
	if c, derr := jam.Dial(); derr != nil {
		jerr = derr
	} else {
		defer c.Close()
		if res, cerr := c.ListPackages(filter); cerr == nil {
			return result(jam.OK(true, map[string]any{
				"count": res["count"], "packages": res["packages"],
			}, ""))
		} else {
			jerr = cerr
		}
	}
	if jerr.Code != "METHOD_NOT_ALLOWED" && jerr.Code != "CONNECTION_FAILED" {
		return result(jam.JamFail(jerr))
	}
	// Fallback adb (host con USB) para APKs antiguas / sin sesión WS.
	out, err := exec.Command("adb", "shell", "pm", "list", "packages").Output()
	if err != nil {
		// Si ya había un fallo WS, es la causa real (adb sin dispositivo).
		if jerr != nil {
			return result(jam.JamFail(jerr))
		}
		return result(jam.Fail("ADB_FAILED", "adb pm list packages falló: "+err.Error(),
			"revisa host adb y conexion del dispositivo"))
	}
	var pkgs []string
	fl := strings.ToLower(filter)
	for _, line := range strings.Split(string(out), "\n") {
		if !strings.HasPrefix(line, "package:") {
			continue
		}
		p := strings.TrimSpace(strings.TrimPrefix(line, "package:"))
		if p == "" {
			continue
		}
		if fl != "" && !strings.Contains(strings.ToLower(p), fl) {
			continue
		}
		pkgs = append(pkgs, p)
	}
	if pkgs == nil {
		pkgs = []string{}
	}
	return result(jam.OK(true, map[string]any{
		"count": len(pkgs), "packages": pkgs,
	}, ""))
}

func hGetForeground(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.GetForeground()
	})
	return result(env)
}

func hOpenApp(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	pkg := getString(args, "package", "")
	if bad := checkPackage(pkg); bad != nil {
		return result(*bad)
	}
	c, jerr := jam.Dial()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	defer c.Close()
	r, jerr := c.OpenApp(pkg)
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	fg, jerr := c.GetForeground()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	if fgPkg, _ := fg["package"].(string); fgPkg != pkg {
		return result(jam.Fail("VERIFY_FAILED", "foreground no es la app pedida",
			"confirma con get_foreground/read_screen; si no llegó, un reintento y luego informe"))
	}
	return result(jam.OK(true, map[string]any{
		"package": pkg, "activity": r["activity"], "foreground": fg,
	}, ""))
}

func hCloseApp(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	pkg := getString(args, "package", "")
	if bad := checkPackage(pkg); bad != nil {
		return result(*bad)
	}
	c, jerr := jam.Dial()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	defer c.Close()
	if _, jerr := c.ForceStop(pkg); jerr != nil {
		return result(jam.JamFail(jerr))
	}
	fg, jerr := c.GetForeground()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	if fgPkg, _ := fg["package"].(string); fgPkg == pkg {
		return result(jam.Fail("VERIFY_FAILED", "la app sigue en foreground",
			"confirma con get_foreground/read_screen; si no salió, un reintento y luego informe"))
	}
	return result(jam.OK(true, map[string]any{
		"package": pkg, "foreground": fg,
	}, ""))
}
