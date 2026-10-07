// Binario jav: servidor MCP por stdio (spec go-migration-plan §2).
// Delgado: lee env, configura logger a stderr, arranca servidor stdio.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"

	"github.com/mark3labs/mcp-go/server"

	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/tools"
)

// version se inyecta por -ldflags -X main.version=… (default 0.1.0).
var version = "0.1.0"

func main() {
	// Logs SOLO a stderr: stdout es framing JSON-RPC puro (spec §3.2).
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	jam.ClientVersion = version

	s := server.NewMCPServer("jav", version, server.WithToolCapabilities(true))
	tools.RegisterAll(s)

	if err := server.ServeStdio(s); err != nil {
		fmt.Fprintf(os.Stderr, "jav: stdio terminó con error: %v\n", err)
		os.Exit(1)
	}
	_ = context.Background
}
