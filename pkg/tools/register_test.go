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
