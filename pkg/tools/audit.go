package tools

import (
	"context"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/jam"
)

// get_audit (Fase 6a): consulta el ring buffer de auditoría del
// dispositivo (AGENTS.md §3.8). Solo metadatos + hash de args, nunca
// contenido en claro. Scope admin.

func hGetAudit(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	limit := getInt(args, "limit", 50)
	if limit < 1 {
		limit = 1
	}
	if limit > 200 {
		limit = 200
	}
	since := getInt64(args, "since_seq", 0)
	if since < 0 {
		since = 0
	}
	return result(jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.GetAudit(limit, since)
	}))
}
