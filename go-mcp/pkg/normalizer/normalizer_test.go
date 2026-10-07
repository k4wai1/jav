package normalizer

import (
	"strings"
	"testing"
)

func dumpWith(nodes ...map[string]any) map[string]any {
	items := make([]any, 0, len(nodes))
	for _, n := range nodes {
		items = append(items, n)
	}
	return map[string]any{"package": "p", "activity": "a", "snapshot_id": 7, "nodes": items}
}

func node(id, class, text string, clickable, editable bool, rid string) map[string]any {
	return map[string]any{"id": id, "class": class, "text": text,
		"content_desc": "", "resource_id": rid, "clickable": clickable,
		"editable": editable, "focused": false, "scrollable": false,
		"visible": true, "bounds": []any{0, 0, 10, 10}}
}

func TestDecorFiltered(t *testing.T) {
	d := dumpWith(
		node("n1", "android.widget.TextView", "hola", false, false, "x:id/ok"),
		node("n2", "android.view.View", "", false, false, "android:id/statusBarBackground"),
		node("n3", "android.widget.LinearLayout", "", false, false, ""),
	)
	st := Normalize(d, MaxCandidates, 100, 100)
	if len(st.Candidates) != 1 || st.Candidates[0].ID != "n1" {
		t.Fatalf("decoración/contenedor deben filtrarse: %+v", st.Candidates)
	}
	if st.RawCount != 3 {
		t.Fatalf("raw_count=%d", st.RawCount)
	}
}

func TestRankEditableFirst(t *testing.T) {
	d := dumpWith(
		node("n1", "android.widget.Button", "ok", true, false, ""),
		node("n2", "android.widget.EditText", "", false, true, ""),
	)
	st := Normalize(d, MaxCandidates, 0, 0)
	if len(st.Candidates) != 2 || !st.Candidates[0].Editable {
		t.Fatalf("editable primero: %+v", st.Candidates)
	}
}

func TestBuildTableCap(t *testing.T) {
	cands := make([]Candidate, 300)
	for i := range cands {
		cands[i] = Candidate{ID: "n", Cls: "Button", Text: "x", Clickable: true, Visible: true}
	}
	rows, byIdx := BuildTable(cands, 0, 0)
	if len(rows) != MaxTable || len(byIdx) != MaxTable {
		t.Fatalf("tabla debe podar a 254: %d", len(rows))
	}
	s := SerializeTable(rows)
	if len(s[0]) != 5 {
		t.Fatalf("fila serializada [idx,class,zone,flags,label]: %v", s[0])
	}
}

func TestZoneOf(t *testing.T) {
	if z := ZoneOf([4]int{0, 0, 10, 10}, 90, 90); z != "top-left" {
		t.Fatalf("zone=%s", z)
	}
	if z := ZoneOf([4]int{0, 0, 10, 10}, 0, 0); z != ZoneUnknown {
		t.Fatalf("sin resolución debe ser unknown: %s", z)
	}
}

func TestValidateTarget(t *testing.T) {
	if bad := ValidateTarget(nil, 0); bad == nil || bad.Code != "SELECTOR_NOT_FOUND" {
		t.Fatalf("nil debe fallar: %+v", bad)
	}
	r := &Row{ID: "n1", Visible: true, Bounds: [4]int{10, 10, 50, 50}}
	if bad := ValidateTarget(r, 200); bad != nil {
		t.Fatalf("válido no debe fallar: %+v", bad)
	}
	r2 := &Row{ID: "n2", Visible: false, Bounds: [4]int{10, 10, 50, 50}}
	if bad := ValidateTarget(r2, 0); bad == nil {
		t.Fatalf("invisible debe fallar")
	}
}

func TestCheckDecisionJSON(t *testing.T) {
	ok := map[string]any{"action": "TAP", "target": 3, "needs_system_2": false, "conf": 0.9}
	if bad := CheckDecisionJSON(ok); bad != nil {
		t.Fatalf("válida no debe fallar: %+v", bad)
	}
	if bad := CheckDecisionJSON(map[string]any{"action": "FLY", "target": 3, "needs_system_2": false, "conf": 0.9}); bad == nil {
		t.Fatalf("action fuera del enum debe fallar")
	}
	if bad := CheckDecisionJSON(map[string]any{"action": "TAP", "target": 999, "needs_system_2": false, "conf": 0.9}); bad == nil {
		t.Fatalf("target fuera de rango debe fallar")
	}
}

func TestIsSensitive(t *testing.T) {
	if !IsSensitive("enviar el reporte", "botón") {
		t.Fatalf("verbo crítico debe detectarse")
	}
	if IsSensitive("abrir la pantalla", "lista") {
		t.Fatalf("goal neutro no debe marcarse")
	}
}

func TestFingerprintStable(t *testing.T) {
	a := []Candidate{{ID: "n1", Text: "hola"}, {ID: "n2", Text: "mundo"}}
	b := []Candidate{{ID: "n2", Text: "mundo"}, {ID: "n1", Text: "hola"}}
	if ScreenFingerprint(a) != ScreenFingerprint(b) {
		t.Fatalf("fingerprint debe ser independiente del orden")
	}
	if !strings.Contains(FormatState(&NormalizedState{Package: "p", SnapshotID: 1, Candidates: a}), "snap=1") {
		t.Fatalf("render debe llevar snapshot")
	}
}
