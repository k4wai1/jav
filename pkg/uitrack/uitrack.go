// Package uitrack mantiene la memoria de proceso de la última lectura de
// pantalla (read_screen): fingerprint vigente, diff contra la lectura previa
// y los nodos ya probados por fingerprint. 100% genérico, sin E/S ni red.
package uitrack

import "sync"

// MaxFingerprints tope de fingerprints con memoria de nodos probados.
const MaxFingerprints = 16

// MaxDiffLabels tope de etiquetas por lista en el diff.
const MaxDiffLabels = 5

// Diff diferencia entre la lectura actual y la anterior.
type Diff struct {
	Changed       bool     `json:"changed"`
	PrevSnapshot  int64    `json:"prev_snapshot_id"`
	SamePackage   bool     `json:"same_package"`
	FocusChanged  bool     `json:"focus_changed"`
	AddedLabels   []string `json:"added_labels"`
	RemovedLabels []string `json:"removed_labels"`
}

type lastRead struct {
	fingerprint string
	snapshotID  int64
	pkg         string
	focusKey    string
	labels      []string
	labelSet    map[string]struct{}
	idxByNode   map[string]int
}

type triedSet struct {
	ids  []string
	seen map[string]struct{}
	idxs map[int]struct{}
}

var (
	mu    sync.Mutex
	last  *lastRead
	order []string
	tried = map[string]*triedSet{}
)

// Observe registra la lectura vigente y devuelve el diff contra la anterior.
// fp/pkgs vacíos se aceptan; idxByNode puede ser nil.
func Observe(fingerprint string, snapshotID int64, pkg, focusKey string, labels []string, idxByNode map[string]int) Diff {
	mu.Lock()
	defer mu.Unlock()

	clean := make([]string, 0, len(labels))
	set := make(map[string]struct{}, len(labels))
	for _, l := range labels {
		if l == "" {
			continue
		}
		if _, dup := set[l]; dup {
			continue
		}
		set[l] = struct{}{}
		clean = append(clean, l)
	}
	if idxByNode == nil {
		idxByNode = map[string]int{}
	}

	d := Diff{SamePackage: true}
	if last == nil {
		d.Changed = true
	} else {
		d.PrevSnapshot = last.snapshotID
		d.SamePackage = last.pkg == pkg
		d.Changed = last.fingerprint != fingerprint
		d.FocusChanged = last.focusKey != focusKey
		if d.Changed {
			d.AddedLabels = added(clean, last.labelSet)
			d.RemovedLabels = removed(last.labels, set)
		}
	}
	last = &lastRead{
		fingerprint: fingerprint, snapshotID: snapshotID, pkg: pkg,
		focusKey: focusKey, labels: clean, labelSet: set, idxByNode: idxByNode,
	}
	touch(fingerprint)
	return d
}

func added(newLabels []string, prev map[string]struct{}) []string {
	out := []string{}
	for _, l := range newLabels {
		if _, ok := prev[l]; !ok {
			out = append(out, l)
			if len(out) >= MaxDiffLabels {
				break
			}
		}
	}
	return out
}

func removed(oldLabels []string, cur map[string]struct{}) []string {
	out := []string{}
	for _, l := range oldLabels {
		if _, ok := cur[l]; !ok {
			out = append(out, l)
			if len(out) >= MaxDiffLabels {
				break
			}
		}
	}
	return out
}

// touch mueve fp al final de la LRU y evicta el más viejo (nunca el vigente).
func touch(fp string) {
	for i, f := range order {
		if f == fp {
			order = append(order[:i], order[i+1:]...)
			break
		}
	}
	order = append(order, fp)
	for len(order) > MaxFingerprints {
		old := order[0]
		order = order[1:]
		if old != fp {
			delete(tried, old)
		}
	}
}

// MarkTried registra un nodo probado contra el fingerprint vigente. Si idx<0
// se resuelve por idxByNode de la última Observe. nodeID vacío es no-op.
func MarkTried(nodeID string, idx int) {
	mu.Lock()
	defer mu.Unlock()
	if last == nil || nodeID == "" {
		return
	}
	fp := last.fingerprint
	if idx < 0 {
		if v, ok := last.idxByNode[nodeID]; ok {
			idx = v
		}
	}
	ts := tried[fp]
	if ts == nil {
		ts = &triedSet{seen: map[string]struct{}{}, idxs: map[int]struct{}{}}
		tried[fp] = ts
	}
	if _, ok := ts.seen[nodeID]; !ok {
		ts.seen[nodeID] = struct{}{}
		ts.ids = append(ts.ids, nodeID)
	}
	if idx >= 0 {
		ts.idxs[idx] = struct{}{}
	}
}

// TriedIDs node_ids probados de un fingerprint (orden de inserción). Copia.
func TriedIDs(fingerprint string) []string {
	mu.Lock()
	defer mu.Unlock()
	ts := tried[fingerprint]
	if ts == nil {
		return []string{}
	}
	out := make([]string, len(ts.ids))
	copy(out, ts.ids)
	return out
}

// CurrentTriedIdx índices probados del fingerprint vigente. Copia.
func CurrentTriedIdx() map[int]bool {
	mu.Lock()
	defer mu.Unlock()
	if last == nil {
		return map[int]bool{}
	}
	ts := tried[last.fingerprint]
	if ts == nil {
		return map[int]bool{}
	}
	out := make(map[int]bool, len(ts.idxs))
	for k := range ts.idxs {
		out[k] = true
	}
	return out
}

// Reset limpia toda la memoria (tests).
func Reset() {
	mu.Lock()
	defer mu.Unlock()
	last = nil
	order = nil
	tried = map[string]*triedSet{}
}
