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
	timeoutMs := getInt(args, "timeout_ms", 15000)
	confirm := getBool(args, "confirm", false)
	if strings.TrimSpace(cmd) == "" {
		return result(validationError("cmd vacío"))
	}
	if timeoutMs < 500 {
		timeoutMs = 500
	}
	if timeoutMs > 60000 {
		timeoutMs = 60000
	}
	return result(jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.Shell(cmd, timeoutMs, confirm)
	}))
}
