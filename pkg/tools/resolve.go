package tools

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/cost"
	"github.com/k4wai1/jav/pkg/director"
	"github.com/k4wai1/jav/pkg/jam"
	"github.com/k4wai1/jav/pkg/normalizer"
)

// hResolveElement expone el resolver ciego de S1 Jev como tool MCP: dump
// fresco + normalizar + tabla vigente + ResolveElementWithTau (tried vigentes
// de pkg/uitrack). No ejecuta nada: devuelve idx/node_id/conf/snapshot_id o el
// Fallback Soberano. 100% genérico, sin literales de app.

func toInt(v any) (int, bool) {
	switch n := v.(type) {
	case int:
		return n, true
	case int64:
		return int(n), true
	case float64:
		return int(n), true
	}
	return 0, false
}

func hResolveElement(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	goal := getString(args, "screen_goal_en", "")
	if strings.TrimSpace(goal) == "" {
		return result(validationError("screen_goal_en vacío"))
	}
	tau := getFloat(args, "tau", director.ResolveTau)
	if tau < 0 || tau > 1 {
		return result(validationError("tau fuera de 0..1"))
	}

	c, jerr := jam.Dial()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}
	defer c.Close()
	dump, jerr := c.DumpUI()
	if jerr != nil {
		return result(jam.JamFail(jerr))
	}

	st := normalizer.Normalize(dump, normalizer.MaxCandidates, ScreenHeight(), ScreenWidth())
	rows, byIdx := normalizer.BuildTable(st.Candidates, ScreenWidth(), ScreenHeight())
	serial := normalizer.SerializeTable(rows)
	var first any
	if fr, ok := normalizer.FirstResult(rows); ok {
		first = fr
	}

	runID := "resolve-" + strconv.FormatInt(nowMs(), 10)
	out, _ := director.ResolveElementWithTau(goal, serial, st.SnapshotID, st.Package, first, nil, cost.NewTracker(runID), runID, tau)

	if fb, _ := out["fallback_required"].(bool); fb {
		env := jam.Fail("RESOLVE_FALLBACK", fmt.Sprint(out["reason"]), director.SovereignRecovery)
		ev := env["evidence"].(map[string]any)
		ev["fallback_required"] = true
		ev["reason"] = out["reason"]
		ev["recovery_instruction"] = out["recovery_instruction"]
		ev["snapshot_id"] = out["snapshot_id"]
		ev["cost"] = cost.SessionSummary()
		for _, k := range []string{"conf", "top_candidates", "cost_usd", "usage"} {
			if v, ok := out[k]; ok {
				ev[k] = v
			}
		}
		return result(env)
	}

	nodeID := ""
	if n, ok := toInt(out["idx"]); ok {
		if row, ok := byIdx[n]; ok {
			nodeID = row.ID
		}
	}
	if nodeID == "" {
		return result(jam.Fail("SELECTOR_NOT_FOUND",
			"el idx resuelto no mapea a un nodo de la tabla vigente",
			"re-haz resolve_element sobre un snapshot fresco"))
	}
	ev := map[string]any{
		"idx": out["idx"], "node_id": nodeID, "conf": out["conf"],
		"snapshot_id": out["snapshot_id"], "fallback_required": false,
		"cost": cost.SessionSummary(),
	}
	for _, k := range []string{"cost_usd", "usage", "mock"} {
		if v, ok := out[k]; ok {
			ev[k] = v
		}
	}
	return result(jam.OK(true, ev, "ejecuta tap_node(node_id, snapshot_id) para el TAP del elemento resuelto"))
}
