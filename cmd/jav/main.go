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

// instructions es el bloque §1 de docs/MCP_SPEC_GUIDELINES.md, verbatim EN
// (salvo versión). Modelo mental mínimo: carriles, frescura, foco,
// verificación, confirmación, privacidad, errores.
const instructions = `You control an Android device through Jav, a bridge to the on-device accessibility service (Jam). You never see pixels unless you ask for a screenshot, and you never invent coordinates: every tap or type targets a node id from a fresh screen snapshot.

LANE HIERARCHY — always prefer the cheapest lane that answers the need:
1. NATIVE first (direct device APIs: battery, memory, storage, cpu, device_info, settings_get, clipboard metadata, usage aggregates, contacts/calendar/notifications/media/location/photo). No UI, nolane switch, no focus needed.
2. INTENTS second (open_url, send_intent): open or pre-fill the target app. Intents never send, post, pay, or delete headlessly: at most they open a pre-filled editor; the send happens in the destination UI or through the UI lane with gates.
3. UI last (read_screen, tap_node, type_text, scroll, press_back, wait_for_text): drive the screen node by node. Slow and stateful; use only when lanes 1-2 cannot satisfy the goal.

FRESHNESS — read_screen returns a monotone snapshot_id. tap_node and type_text REQUIRE the snapshot_id you just read; if the UI changed since, they fail with STALE_SNAPSHOT. Never retry the same snapshot: re-read and resolve the node again (one retry; a second STALE means the screen is unstable — stop and report UI_UNSTABLE).

FOCUS — type_text only writes into the focused field (REPLACE semantics via ACTION_SET_TEXT, no simulated keyboard, no append). If the node is not focused you get NOT_FOCUSED: tap the field first, re-read, then type. There are no implicit taps.

VERIFY — actions never return a snapshot. After every mutation, verify with read_screen or wait_for_text and report what changed. Prefer tap_node over tap-by-text when you already hold a fresh snapshot (no internal re-dump). Prefer ACTION_CLICK paths (clickable nodes) and expect the result field via telling which path executed.

CONFIRM — critical or irreversible effects (messaging third parties, buying/paying, deleting data, account/security/permission changes, photo capture, media stop, settings writes) NEVER execute on first call: they answer {planned:true, preview, hint} with verified:false. Repeat with confirm:true only after the operator approved the exact preview. Previews carry lengths/hashes, never raw sensitive text.

PRIVACY — clipboard, contacts, calendar, notifications, and location are minimal-projection: counts/hashes/lengths in logs, never raw content beyond what the task strictly needs. Never log secrets, tokens, or full message bodies.

ERRORS — every failure carries a machine code in evidence.code plus a human recovery instruction in hint. Follow the hint literally; it is part of the contract (see the per-tool Errors section for the catalog).`

func main() {
	// Logs SOLO a stderr: stdout es framing JSON-RPC puro (spec §3.2).
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	jam.ClientVersion = version

	s := server.NewMCPServer("jav", version,
		server.WithToolCapabilities(true),
		server.WithInstructions(instructions),
	)
	tools.RegisterAll(s)
	tools.RegisterExtras(s)

	if err := server.ServeStdio(s); err != nil {
		fmt.Fprintf(os.Stderr, "jav: stdio terminó con error: %v\n", err)
		os.Exit(1)
	}
	_ = context.Background
}
