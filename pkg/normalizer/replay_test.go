package normalizer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Replay conductual Go vs Python (ui_normalizer.py + loop_helpers.py puros).
//
// Cobertura real (no inventada):
// - logs/run-*.jsonl NO trae árbol crudo: forense por fase
//   (snapshot/n_cands/render) o conteos ("nodes":12).
//   Ninguna línea trae "nodes" como array de nodos con "class".
// - Este test usa 2 dumps reales con árbol crudo (vendorizados en testdata/
//   tras la purga del servidor Python; Go autocontenido, sin dependencia Python):
//   (1) testdata/wa_home.json (174 nodos reales)
//   (2) testdata/jam_live_18.json (Jam onboarding real en 5002E e03638e5,
//       capturado vía dump_ui, 18 nodos).
// - El esperado (testdata/replay_expected.json) lo generó Python
//   (normalize + build_table + serialize_table + zone_of, 720x1440).
//   Go debe dar poda/índices/zonas 3×3 idénticos.

type replayDump struct {
	Name string
	Path string
}

func loadDump(t *testing.T, path string) map[string]any {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("leer %s: %v", path, err)
	}
	var dump map[string]any
	if err := json.Unmarshal(raw, &dump); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	return dump
}

func TestLogsSinArbolCrudo(t *testing.T) {
	roots := []string{"../../logs"}
	total := 0
	withRaw := 0
	for _, root := range roots {
		files, _ := filepath.Glob(filepath.Join(root, "run-*.jsonl"))
		for _, f := range files {
			raw, err := os.ReadFile(f)
			if err != nil {
				continue
			}
			total++
			// Árbol crudo = alguna línea con "nodes": [ {..class..} ].
			// Los logs solo traen conteos ("nodes":12) o render.
			for _, line := range strings.Split(string(raw), "\n") {
				line = strings.TrimSpace(line)
				if line == "" || !strings.Contains(line, `"nodes"`) {
					continue
				}
				var obj map[string]any
				if err := json.Unmarshal([]byte(line), &obj); err != nil {
					continue
				}
				if arr, ok := obj["nodes"].([]any); ok && len(arr) > 0 {
					if m, ok := arr[0].(map[string]any); ok {
						if _, hasClass := m["class"]; hasClass {
							withRaw++
							break
						}
					}
				}
			}
		}
	}
	t.Logf("logs run-*.jsonl: total=%d con_arbol_crudo=%d (cobertura replay = fixtures, no logs)", total, withRaw)
	if withRaw != 0 {
		t.Fatalf("se esperaban 0 logs con árbol crudo, hay %d", withRaw)
	}
	if total == 0 {
		t.Fatalf("no se encontraron logs run-*.jsonl para documentar cobertura")
	}
}

func TestReplayPythonParity(t *testing.T) {
	expRaw, err := os.ReadFile("testdata/replay_expected.json")
	if err != nil {
		t.Fatalf("leer replay_expected.json: %v", err)
	}
	var exp struct {
		ScreenW int `json:"screen_w"`
		ScreenH int `json:"screen_h"`
		Dumps   map[string]struct {
			Package    string     `json:"package"`
			SnapshotID int64      `json:"snapshot_id"`
			RawCount   int        `json:"raw_count"`
			NCands     int        `json:"n_cands"`
			Compact    []string   `json:"compact"`
			Table      [][]any    `json:"table"`
			Zones      []string   `json:"zones"`
			IDs        []string   `json:"ids"`
		} `json:"dumps"`
	}
	if err := json.Unmarshal(expRaw, &exp); err != nil {
		t.Fatalf("parse replay_expected.json: %v", err)
	}
	dumps := []replayDump{
		{"wa_home", "testdata/wa_home.json"},
		{"jam_live_18", "testdata/jam_live_18.json"},
	}
	if len(dumps) < 2 {
		t.Fatalf("se exigen >=2 dumps reales")
	}
	for _, d := range dumps {
		want, ok := exp.Dumps[d.Name]
		if !ok {
			t.Fatalf("sin esperado Python para %s", d.Name)
		}
		dump := loadDump(t, d.Path)
		st := Normalize(dump, MaxCandidates, exp.ScreenH, exp.ScreenW)
		if st.RawCount != want.RawCount {
			t.Fatalf("%s raw_count Go=%d Python=%d", d.Name, st.RawCount, want.RawCount)
		}
		if len(st.Candidates) != want.NCands {
			t.Fatalf("%s poda Go=%d Python=%d", d.Name, len(st.Candidates), want.NCands)
		}
		gotCompact := st.CompactLines()
		if len(gotCompact) != len(want.Compact) {
			t.Fatalf("%s compact len Go=%d Python=%d", d.Name, len(gotCompact), len(want.Compact))
		}
		for i := range gotCompact {
			if gotCompact[i] != want.Compact[i] {
				t.Fatalf("%s compact[%d] Go=%q Python=%q", d.Name, i, gotCompact[i], want.Compact[i])
			}
		}
		rows, _ := BuildTable(st.Candidates, exp.ScreenW, exp.ScreenH)
		if len(rows) != len(want.IDs) {
			t.Fatalf("%s tabla Go=%d Python=%d", d.Name, len(rows), len(want.IDs))
		}
		for i, r := range rows {
			if r.ID != want.IDs[i] {
				t.Fatalf("%s índice[%d] Go id=%q Python=%q", d.Name, i, r.ID, want.IDs[i])
			}
			if r.Zone != want.Zones[i] {
				t.Fatalf("%s zona[%d] Go=%q Python=%q bounds=%v", d.Name, i, r.Zone, want.Zones[i], r.Bounds)
			}
		}
		gotSer := SerializeTable(rows)
		if len(gotSer) != len(want.Table) {
			t.Fatalf("%s serialize len Go=%d Python=%d", d.Name, len(gotSer), len(want.Table))
		}
		for i := range gotSer {
			// [idx, class_short, zone, flags, label]
			gj, _ := json.Marshal(gotSer[i])
			pj, _ := json.Marshal(want.Table[i])
			if string(gj) != string(pj) {
				t.Fatalf("%s fila[%d] Go=%s Python=%s", d.Name, i, gj, pj)
			}
		}
		t.Logf("%s OK: raw=%d cands=%d rows=%d (paridad Python exacta)", d.Name, st.RawCount, len(st.Candidates), len(rows))
	}
}
