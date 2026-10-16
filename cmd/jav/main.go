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

// version se inyecta por -ldflags -X main.version=… (default 1.2.1).
var version = "1.2.1"

// instructions es el bloque §1 de docs/MCP_SPEC_GUIDELINES.md, compactado a
// ≤220 palabras (v1.2.0). Conserva intactos los tokens obligatorios
// (LANE, snapshot_id, NOT_FOCUSED, VERIFY, planned:true, confirm:true,
// PRIVACY, hint) y remite a las fichas completas bajo demanda por Resource.
const instructions = `You control an Android device through Jav, bridging the on-device accessibility service. Never invent coordinates: taps/types target a node id from a fresh snapshot.

LANE — prefer the cheapest lane: (1) NATIVE device APIs (battery, memory, storage, cpu, device_info, settings, clipboard, usage, contacts, calendar, notifications, media, location, photo); (2) INTENTS (open_url, send_intent) that open or pre-fill, never send headlessly; (3) UI last (read_screen, tap_node, type_text, scroll, press_back, wait_for_text).

FRESHNESS — read_screen returns a monotone snapshot_id; tap_node and type_text REQUIRE it, else STALE_SNAPSHOT. Never retry the same snapshot: re-read once; a second STALE means UI_UNSTABLE — stop and report.

FOCUS — type_text writes only into the focused field (REPLACE via ACTION_SET_TEXT). Otherwise NOT_FOCUSED: tap, re-read, then type. No implicit taps.

VERIFY — mutations return no snapshot; verify with read_screen or wait_for_text and report the via path executed. Prefer tap_node over tap-by-text.

CONFIRM — critical/irreversible effects (messaging, paying, deleting, account/permission, photo, media stop, settings writes) return {planned:true, preview, hint} with verified:false on first call. Repeat with confirm:true only after the operator approves that exact preview. Previews carry lengths/hashes, never raw secrets.

PRIVACY — clipboard/contacts/calendar/notifications/location are minimal-projection: counts/hashes/lengths, never raw content beyond the task; never log secrets or bodies.

ERRORS — every failure carries evidence.code plus a recovery hint; follow it literally. Full per-tool specs load on demand: android://tool/<name> or android://tools/catalog.`

func main() {
	// Subcomando de vinculación sin fricción (no arranca el servidor MCP):
	//   jav pair <ip-o-url> <token> [openrouter_api_key]
	if len(os.Args) > 1 && os.Args[1] == "pair" {
		os.Exit(runPair(os.Args[2:]))
	}
	// Logs SOLO a stderr: stdout es framing JSON-RPC puro (spec §3.2).
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	jam.ClientVersion = version

	s := server.NewMCPServer("jav", version,
		server.WithToolCapabilities(true),
		server.WithInstructions(instructions),
	)
	tools.RegisterAll(s)
	tools.RegisterExtras(s)
	tools.RegisterSpecResources(s)

	if err := server.ServeStdio(s); err != nil {
		fmt.Fprintf(os.Stderr, "jav: stdio terminó con error: %v\n", err)
		os.Exit(1)
	}
	_ = context.Background
}
