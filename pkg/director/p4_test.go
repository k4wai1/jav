package director

import (
	"strings"
	"testing"

	"github.com/k4wai1/jav/pkg/jev"
)

func TestBuildResolveStateWithTried(t *testing.T) {
	serial := []jev.SerialRow{
		{0, "Button", "top-left", "click", "a"},
		{1, "Button", "top-right", "click", "b"},
		{2, "Button", "mid-center", "—", "c"},
	}
	state, _ := BuildResolveStateWithTried("goal", serial, 9, "com.example", nil, map[int]bool{1: true, 2: true})
	rows, ok := state["table"].([]jev.SerialRow)
	if !ok || len(rows) != 3 {
		t.Fatalf("table copiada: %v", state["table"])
	}
	if !strings.Contains(rows[1][3].(string), "tried") {
		t.Fatalf("fila probada debe llevar tried: %v", rows[1][3])
	}
	if strings.Contains(rows[0][3].(string), "tried") {
		t.Fatalf("fila no probada sin tried: %v", rows[0][3])
	}
	if rows[2][3] != "tried" {
		t.Fatalf("flags — pasa a tried: %v", rows[2][3])
	}
	if serial[1][3] != "click" || serial[2][3] != "—" {
		t.Fatalf("no debe mutar la entrada: %v", serial)
	}
}

func TestBuildResolveStateWithoutTriedUnchanged(t *testing.T) {
	serial := []jev.SerialRow{{0, "Button", "top-left", "click", "a"}}
	state, _ := BuildResolveState("goal", serial, 9, "com.example", nil)
	rows, _ := state["table"].([]jev.SerialRow)
	if rows[0][3] != "click" {
		t.Fatalf("sin triedIdx no debe marcarse: %v", rows[0][3])
	}
}
