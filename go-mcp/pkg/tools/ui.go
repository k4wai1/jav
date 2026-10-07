package tools

import (
	"context"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/k4wai1/jav/pkg/jam"
)

// Handlers ui/ (equiv. tools/ui.py). Sin post-snapshot; tap_node/type_text
// exigen snapshot_id (STALE_SNAPSHOT si rotó, lo decide Jam).

func hReadScreen(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	return result(readScreenState())
}

func hTapText(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	text := getString(args, "text", "")
	if text == "" {
		return result(validationError("text vacío"))
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.Tap(map[string]any{"text_contains": text})
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		env = jam.OK(true, map[string]any{"node_id": ev["node_id"], "via": ev["via"]},
			"verifica el efecto con read_screen")
	}
	return result(env)
}

func hTapNode(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	nodeID := getString(args, "node_id", "")
	snap := getInt64(args, "snapshot_id", -1)
	if nodeID == "" {
		return result(validationError("node_id vacío"))
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.TapNode(nodeID, snap)
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		env = jam.OK(true, map[string]any{"node_id": ev["node_id"], "via": ev["via"]},
			"verifica el efecto con read_screen")
	}
	return result(env)
}

func hTypeText(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	nodeID := getString(args, "node_id", "")
	snap := getInt64(args, "snapshot_id", -1)
	text := getString(args, "text", "")
	if nodeID == "" {
		return result(validationError("node_id vacío"))
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.TypeText(nodeID, snap, text)
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		var chars any = ev["chars"]
		if chars == nil {
			chars = 0
		}
		env = jam.OK(true, map[string]any{"chars": chars, "snapshot_id": snap},
			"verifica el efecto con read_screen")
	}
	return result(env)
}

func hScroll(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	direction := getString(args, "direction", "down")
	nodeID := getNullableString(args, "node_id")
	if bad := checkDirection(direction); bad != nil {
		return result(*bad)
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.Scroll(direction, nodeID)
	})
	if ok, _ := env["ok"].(bool); ok {
		env = jam.OK(true, map[string]any{"direction": direction},
			"verifica el efecto con read_screen")
	}
	return result(env)
}

func hPressBack(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.PressBack()
	})
	if ok, _ := env["ok"].(bool); ok {
		env = jam.OK(true, map[string]any{"action": "press_back"},
			"verifica el efecto con read_screen")
	}
	return result(env)
}

func hPressHome(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.PressHome()
	})
	if ok, _ := env["ok"].(bool); ok {
		env = jam.OK(true, map[string]any{"action": "press_home"}, "")
	}
	return result(env)
}

func hWaitForText(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	text := getString(args, "text", "")
	timeoutMs := getInt(args, "timeout_ms", 5000)
	if text == "" {
		return result(validationError("text vacío"))
	}
	if timeoutMs < 0 {
		return result(validationError("timeout_ms negativo"))
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.WaitForNode(map[string]any{"text_contains": text}, timeoutMs)
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		env = jam.OK(true, map[string]any{
			"node_id": ev["node_id"], "snapshot_id": ev["snapshot_id"],
		}, "usa snapshot_id directo en tap_node si no hubo cambios")
	}
	return result(env)
}

func hScreenshot(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := argsOf(req)
	fmtStr := getString(args, "fmt", "png")
	quality := getInt(args, "quality", 80)
	if bad := checkFmt(fmtStr); bad != nil {
		return result(*bad)
	}
	if quality < 0 || quality > 100 {
		return result(validationError("quality fuera de 0..100"))
	}
	env := jamCall(func(c *jam.Client) (map[string]any, *jam.JamError) {
		return c.Screenshot(fmtStr, quality)
	})
	if ok, _ := env["ok"].(bool); ok {
		ev := env["evidence"].(map[string]any)
		env = jam.OK(true, map[string]any{
			"w": ev["w"], "h": ev["h"], "via": ev["via"],
			"img_base64": ev["img_base64"],
		}, "")
	}
	return result(env)
}
