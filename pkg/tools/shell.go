package tools

import (
	"context"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/jam"
)

// adb_shell (Fase 6b): comando arbitrario con UID shell vía Shizuku.
// Scope admin; gate triple en Jav: rate limit 5/s → denylist → grant
// interactivo. Nunca `su` (AGENTS.md §2). El mapeo tool↔método es
// adb_shell ↔ shell (AGENTS.md §6).

func hAdbShell(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	cmd := getString(args, "cmd", "")
	timeoutMs := getInt(args, "timeout_ms", 65000)
	confirm := getBool(args, "confirm", false)
	if strings.TrimSpace(cmd) == "" {
		return result(validationError("cmd vacío"))
	}
	if timeoutMs < 500 {
		timeoutMs = 500
	}
	// v2.3.1: el grant ya NO bloquea el WS (sin grant → planned +
	// grant_pending). El default sigue cubriendo comandos largos tras
	// aprobar, sin forzar al agente a subirlo en cada llamada.
	if timeoutMs > 90000 {
		timeoutMs = 90000
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.Shell(cmd, timeoutMs, confirm)
	})
	if ev, ok := env["evidence"].(map[string]any); ok {
		if p, _ := ev["grant_pending"].(bool); p {
			env["hint"] = "aprueba la notificación (1 cmd / 5 min / 30 min) y repite el mismo comando"
		}
	}
	return result(env)
}
