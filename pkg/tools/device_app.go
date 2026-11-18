package tools

import (
	"context"
	"os/exec"
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
	t0 := nowMs()
	c, jerr := jam.Dial()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	defer c.Close()
	fg, jerr := c.GetForeground()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	_ = t0
	// caps del hello (v1.2.5): evita que el agente adivine grants; app
	// <1.2.5 o hello sin caps → objeto vacío (no se inventa estado).
	caps := c.Caps
	if caps == nil {
		caps = map[string]bool{}
	}
	return result(jam.OK(true, map[string]any{
		"scopes": c.Scopes, "app_version": c.AppVersion, "foreground": fg,
		"caps": caps, "cost": cost.SessionSummary(),
		"active_device": jam.ActiveDeviceName(), "paired_devices": jam.PairedDeviceNames(),
	}, ""))
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
