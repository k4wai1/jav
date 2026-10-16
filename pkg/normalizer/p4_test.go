package normalizer

import "testing"

func p4Dump(nodes []map[string]any) map[string]any {
	arr := make([]any, len(nodes))
	for i, n := range nodes {
		arr[i] = n
	}
	return map[string]any{"package": "com.example.app", "snapshot_id": int64(7), "nodes": arr}
}

func TestP4FocusedFieldPasswordByMarker(t *testing.T) {
	st := Normalize(p4Dump([]map[string]any{{
		"id": "n1", "class": "android.widget.EditText",
		"resource_id": "com.example.app:id/password",
		"text":        "hunter2", "editable": true, "focused": true,
		"bounds": []any{0, 0, 100, 50},
	}}), MaxCandidates, 800, 480)
	v := st.Focused.AsView()
	if v["kind"] != "password" || v["holds"] != PassMask {
		t.Fatalf("debe enmascarar password: %v", v)
	}
	if v["label"] == "hunter2" || v["holds"] == "hunter2" {
		t.Fatalf("no debe filtrar el secreto: %v", v)
	}
}

func TestP4FocusedFieldPasswordNative(t *testing.T) {
	st := Normalize(p4Dump([]map[string]any{{
		"id": "n1", "class": "android.widget.EditText",
		"resource_id": "com.example.app:id/field",
		"text":        "1234", "editable": true, "focused": true, "password": true,
		"bounds": []any{0, 0, 100, 50},
	}}), MaxCandidates, 800, 480)
	v := st.Focused.AsView()
	if v["kind"] != "password" || v["holds"] != PassMask {
		t.Fatalf("propiedad nativa password debe enmascarar: %v", v)
	}
}

func TestP4FocusedFieldTextNormal(t *testing.T) {
	st := Normalize(p4Dump([]map[string]any{{
		"id": "n1", "class": "android.widget.EditText",
		"text": "hola mundo", "editable": true, "focused": true,
		"bounds": []any{0, 0, 100, 50},
	}}), MaxCandidates, 800, 480)
	v := st.Focused.AsView()
	if v["kind"] != "text" || v["holds"] != "hola mundo" {
		t.Fatalf("texto normal sin máscara: %v", v)
	}
}

func TestP4ScreenFingerprintRows(t *testing.T) {
	c := []Candidate{
		{ID: "n1", Cls: "TextView", Text: "Enviar"},
		{ID: "n2", Cls: "TextView", Text: "9:41"},
	}
	rows, _ := BuildTable(c, 480, 800)
	fp := ScreenFingerprintRows("com.a", rows)
	if len(fp) != 12 {
		t.Fatalf("fingerprint debe ser 12 hex: %q", fp)
	}
	if ScreenFingerprintRows("com.a", rows) != fp {
		t.Fatalf("fingerprint debe ser determinista")
	}
	if ScreenFingerprintRows("com.b", rows) == fp {
		t.Fatalf("el paquete debe cambiar la firma")
	}
	c2 := []Candidate{
		{ID: "n1", Cls: "TextView", Text: "Enviar"},
		{ID: "n2", Cls: "TextView", Text: "10:59"},
	}
	rows2, _ := BuildTable(c2, 480, 800)
	if ScreenFingerprintRows("com.a", rows2) != fp {
		t.Fatalf("el reloj volátil no debe cambiar la firma")
	}
}

func TestP4ScreenFingerprintRowsEmpty(t *testing.T) {
	rows, _ := BuildTable([]Candidate{{ID: "n1", Cls: "TextView", Text: "9:41"}}, 480, 800)
	if ScreenFingerprintRows("com.a", rows) != "" {
		t.Fatalf("sin filas estables la firma debe ser vacía")
	}
}

func TestP4AddFlag(t *testing.T) {
	if AddFlag("click", TriedFlag) != "click|tried" {
		t.Fatalf("flag sobre click")
	}
	if AddFlag(EmptyFlags, TriedFlag) != TriedFlag {
		t.Fatalf("— equivale a vacío")
	}
	if AddFlag("click|tried", TriedFlag) != "click|tried" {
		t.Fatalf("flag idempotente")
	}
	if AddFlag("click", "") != "click" {
		t.Fatalf("flag vacío no-op")
	}
}
