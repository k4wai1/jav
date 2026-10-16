package tools

import (
	"encoding/json"
	"testing"
)

func TestSchemasMirrorPython(t *testing.T) {
	cases := []struct {
		name     string
		required []string
		props    map[string]any
	}{
		{"tap_node", []string{"node_id", "snapshot_id"}, map[string]any{
			"node_id": strReq("node_id"), "snapshot_id": intReq("snapshot_id")}},
		{"scroll", nil, map[string]any{
			"direction": strProp("direction", "down"), "node_id": nullableStrProp("node_id")}},
		{"send_intent", []string{"action"}, map[string]any{
			"action": strReq("action"), "extras": extrasProp()}},
		{"resolve_element", []string{"screen_goal_en"}, map[string]any{
			"screen_goal_en": strReq("screen_goal_en"), "tau": numProp("tau", 0.70)}},
	}
	for _, c := range cases {
		raw := rawSchema(c.name, c.required, c.props)
		var obj map[string]any
		if err := json.Unmarshal(raw, &obj); err != nil {
			t.Fatalf("%s: schema no-JSON: %v", c.name, err)
		}
		if obj["type"] != "object" || obj["title"] != c.name+"Arguments" {
			t.Fatalf("%s: envelope: %v", c.name, obj)
		}
	}
}

func TestToolDefsCount(t *testing.T) {
	if len(toolDefs) != 38 {
		t.Fatalf("tools=%d, se esperan 38", len(toolDefs))
	}
	seen := map[string]bool{}
	for _, d := range toolDefs {
		if seen[d.name] {
			t.Fatalf("tool duplicada: %s", d.name)
		}
		seen[d.name] = true
	}
	if !seen["resolve_element"] {
		t.Fatalf("falta resolve_element")
	}
	if !seen["get_audit"] {
		t.Fatalf("falta get_audit")
	}
	if !seen["adb_shell"] {
		t.Fatalf("falta adb_shell")
	}
}

func TestClientSideValidation(t *testing.T) {
	if bad := checkDirection("diagonal"); bad == nil {
		t.Fatalf("direction inválida debe fallar")
	}
	if bad := checkDirection("down"); bad != nil {
		t.Fatalf("down válido: %v", bad)
	}
	if bad := checkPackage("no-es-paquete"); bad == nil {
		t.Fatalf("package con mala forma debe fallar")
	}
	if bad := checkPackage("com.example.app"); bad != nil {
		t.Fatalf("package válido: %v", bad)
	}
	if bad := checkURL("sin-esquema"); bad == nil {
		t.Fatalf("url sin :// debe fallar")
	}
	if bad := checkCamera("side"); bad == nil {
		t.Fatalf("camera inválida debe fallar")
	}
}
