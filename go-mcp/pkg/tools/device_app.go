package tools

import (
	"context"
	"os/exec"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/jam"
)

// Handlers device/ + app/ (equiv. tools/device.py + tools/app.py).

func hDeviceStatus(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
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
	return result(jam.OK(true, map[string]any{
		"scopes": c.Scopes, "app_version": c.AppVersion, "foreground": fg,
	}, ""))
}

func hListPackages(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	filter := getString(args, "filter", "")
	// Host adb, nunca vía WS (igual que Python).
	out, err := exec.Command("adb", "shell", "pm", "list", "packages").Output()
	if err != nil {
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
