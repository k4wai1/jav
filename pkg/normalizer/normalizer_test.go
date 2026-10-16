package normalizer

import (
	"encoding/json"
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

func TestFingerprintIgnoresVolatile(t *testing.T) {
	a := []Candidate{{ID: "n1", Text: "Enviar"}, {ID: "n2", Text: "9:40"}}
	b := []Candidate{{ID: "n1", Text: "Enviar"}, {ID: "n2", Text: "9:41"}}
	if ScreenFingerprint(a) != ScreenFingerprint(b) {
		t.Fatalf("el reloj no debe cambiar la firma")
	}
	c := []Candidate{{ID: "n1", Text: "Enviar"}, {ID: "n2", Desc: "12:00:00"}}
	d := []Candidate{{ID: "n1", Text: "Enviar"}}
	if ScreenFingerprint(c) != ScreenFingerprint(d) {
		t.Fatalf("reloj en desc no debe cambiar la firma")
	}
	e := []Candidate{{ID: "n1", Text: "Enviar"}, {ID: "n2", Text: "78 %"}}
	f := []Candidate{{ID: "n1", Text: "Enviar"}, {ID: "n2", Text: "79%"}}
	if ScreenFingerprint(e) != ScreenFingerprint(f) {
		t.Fatalf("la batería no debe cambiar la firma")
	}
}

func TestFingerprintEmptyWhenAllVolatile(t *testing.T) {
	s := ScreenFingerprint([]Candidate{{ID: "n2", Text: "9:41"}, {ID: "n3", Text: "78%"}})
	if s != "" {
		t.Fatalf("firma sin contenido estable debe ser vacía, got %q", s)
	}
}

func TestP5SecretNeverLeaks(t *testing.T) {
	secret := "hunter2-s3cr3t"
	d := dumpWith(
		map[string]any{"id": "n1", "class": "android.widget.EditText",
			"text": secret, "content_desc": "", "resource_id": "",
			"clickable": false, "editable": true, "focused": true,
			"scrollable": false, "visible": true, "password": true,
			"bounds": []any{0, 0, 100, 50}},
		map[string]any{"id": "n2", "class": "android.widget.EditText",
			"text": secret, "content_desc": "Contraseña", "resource_id": "com.example.app:id/password",
			"clickable": false, "editable": true, "focused": false,
			"scrollable": false, "visible": true,
			"bounds": []any{0, 0, 100, 50}},
		node("n3", "android.widget.Button", "Enviar", true, false, ""),
	)
	st := Normalize(d, MaxCandidates, 800, 480)

	if st.Focused == nil {
		t.Fatalf("debe haber campo enfocado")
	}
	fv := st.Focused.AsView()
	if fv["kind"] != "password" || fv["holds"] != PassMask || fv["label"] == secret {
		t.Fatalf("focused_field no debe filtrar el secreto: %v", fv)
	}
	render := FormatState(st)
	if strings.Contains(render, secret) {
		t.Fatalf("render no debe contener el secreto: %q", render)
	}
	rows, _ := BuildTable(st.Candidates, 480, 800)
	for _, fr := range SerializeTable(rows) {
		blob, _ := json.Marshal(fr)
		if strings.Contains(string(blob), secret) {
			t.Fatalf("tabla no debe contener el secreto: %s", blob)
		}
	}
	for _, c := range st.Candidates {
		if c.SafeText() == secret || strings.Contains(c.Compact(), secret) {
			t.Fatalf("candidates no debe contener el secreto: %+v", c)
		}
	}
}

func TestP5SecretLabelFallback(t *testing.T) {
	c := Candidate{ID: "", Cls: "EditText", Text: "x", Secret: true}
	if got := c.Compact(); !strings.Contains(got, SecretMask) {
		t.Fatalf("sin etiqueta derivable debe usar %q: %q", SecretMask, got)
	}
	if c.SafeText() != SecretMask {
		t.Fatalf("SafeText sin etiqueta debe ser %q: %q", SecretMask, c.SafeText())
	}
	c2 := Candidate{ID: "n9", Cls: "EditText", Text: "x", Desc: "Contraseña", Secret: true}
	if got := c2.Compact(); !strings.Contains(got, "Contraseña") || strings.Contains(got, "\"x\"") {
		t.Fatalf("debe usar content_desc como etiqueta: %q", got)
	}
}

func TestFormatCandidateLabel(t *testing.T) {
	cases := map[string]string{
		"9":      "9 [digit nine]",
		"×":      "× [multiplication sign]",
		"+":      "+ [plus sign]",
		"-":      "- [minus sign]",
		"C":      "C [clear]",
		".":      ". [decimal point]",
		" 9 ":    "9 [digit nine]",
		"c":      "c",
		"99":     "99",
		"+1":     "+1",
		"Enviar": "Enviar",
		"":       "",
	}
	for in, want := range cases {
		if got := FormatCandidateLabel(in); got != want {
			t.Fatalf("FormatCandidateLabel(%q)=%q want %q", in, got, want)
		}
	}
}

func TestSanitizeModelLabel(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"vacio", "", ""},
		{"estable", "OK", "OK"},
		{"lf", "a\nb", "ab"},
		{"crlf", "a\r\nb", "ab"},
		{"tab", "a\tb", "ab"},
		{"zwsp", "a\u200bb", "ab"},
		{"zwnj_espacio", "a\u200e b", "a b"},
		{"espacios_multiples", "a   b", "a b"},
		{"recorte", "9  ", "9"},
		{"trunca_ascii", strings.Repeat("a", 100), strings.Repeat("a", 80)},
		{"trunca_runas_multibyte", strings.Repeat("€", 100), strings.Repeat("€", 80)},
		{"nbsp_intacto", "a\u00a0\u00a0b", "a\u00a0\u00a0b"},
	}
	for _, c := range cases {
		if got := SanitizeModelLabel(c.in); got != c.want {
			t.Fatalf("%s: SanitizeModelLabel(%q)=%q want %q", c.name, c.in, got, c.want)
		}
	}
}
