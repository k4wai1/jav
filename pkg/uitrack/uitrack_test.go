package uitrack

import (
	"fmt"
	"testing"
)

func TestObserveFirstRead(t *testing.T) {
	Reset()
	d := Observe("f1", 5, "pkg", "lbl\x00text", []string{"a", "b"}, nil)
	if !d.Changed || d.PrevSnapshot != 0 || !d.SamePackage || d.FocusChanged {
		t.Fatalf("primera lectura: %+v", d)
	}
	if len(d.AddedLabels) != 0 || len(d.RemovedLabels) != 0 {
		t.Fatalf("primera lectura sin listas: %+v", d)
	}
}

func TestObserveNoChange(t *testing.T) {
	Reset()
	Observe("f1", 5, "pkg", "k", []string{"a", "b"}, nil)
	d := Observe("f1", 6, "pkg", "k", []string{"a", "b"}, nil)
	if d.Changed || d.PrevSnapshot != 5 || !d.SamePackage || d.FocusChanged {
		t.Fatalf("sin cambios: %+v", d)
	}
	if len(d.AddedLabels) != 0 || len(d.RemovedLabels) != 0 {
		t.Fatalf("sin cambios sin listas: %+v", d)
	}
}

func TestObserveAddedRemovedFocus(t *testing.T) {
	Reset()
	Observe("f1", 5, "pkg", "k1", []string{"a", "b"}, nil)
	d := Observe("f2", 9, "pkg", "k2", []string{"b", "c"}, nil)
	if !d.Changed || d.PrevSnapshot != 5 || !d.SamePackage || !d.FocusChanged {
		t.Fatalf("cambio: %+v", d)
	}
	if len(d.AddedLabels) != 1 || d.AddedLabels[0] != "c" {
		t.Fatalf("added: %+v", d.AddedLabels)
	}
	if len(d.RemovedLabels) != 1 || d.RemovedLabels[0] != "a" {
		t.Fatalf("removed: %+v", d.RemovedLabels)
	}
}

func TestObserveDifferentPackage(t *testing.T) {
	Reset()
	Observe("f1", 1, "pkg.a", "k", nil, nil)
	d := Observe("f2", 2, "pkg.b", "k", nil, nil)
	if d.SamePackage {
		t.Fatalf("paquete distinto: %+v", d)
	}
}

func TestObserveLabelsCapped(t *testing.T) {
	Reset()
	Observe("f1", 1, "pkg", "k", nil, nil)
	d := Observe("f2", 2, "pkg", "k", []string{"1", "2", "3", "4", "5", "6", "7"}, nil)
	if len(d.AddedLabels) != MaxDiffLabels {
		t.Fatalf("tope de %d etiquetas: %+v", MaxDiffLabels, d.AddedLabels)
	}
}

func TestTriedPerFingerprintAndClearedOnScreenChange(t *testing.T) {
	Reset()
	Observe("fp1", 1, "pkg", "k", nil, map[string]int{"n1": 0, "n2": 1})
	MarkTried("n1", -1)
	MarkTried("n2", -1)
	ids := TriedIDs("fp1")
	if len(ids) != 2 || ids[0] != "n1" || ids[1] != "n2" {
		t.Fatalf("tried fp1: %+v", ids)
	}
	if idx := CurrentTriedIdx(); !idx[0] || !idx[1] || len(idx) != 2 {
		t.Fatalf("idx fp1: %+v", idx)
	}
	Observe("fp2", 2, "pkg", "k", nil, nil)
	if len(TriedIDs("fp2")) != 0 || len(CurrentTriedIdx()) != 0 {
		t.Fatalf("pantalla nueva debe empezar sin tried")
	}
	if len(TriedIDs("fp1")) != 2 {
		t.Fatalf("fp1 conserva su memoria")
	}
}

func TestTriedExplicitIdx(t *testing.T) {
	Reset()
	Observe("fp1", 1, "pkg", "k", nil, nil)
	MarkTried("nx", 42)
	if idx := CurrentTriedIdx(); !idx[42] {
		t.Fatalf("idx explícito: %+v", idx)
	}
}

func TestMarkTriedNoopWithoutObserve(t *testing.T) {
	Reset()
	MarkTried("n1", -1)
	MarkTried("", 3)
	if len(CurrentTriedIdx()) != 0 {
		t.Fatalf("sin lectura no hay tried")
	}
}

func TestTriedBounded(t *testing.T) {
	Reset()
	for i := 0; i < MaxFingerprints+8; i++ {
		fp := fmt.Sprintf("fp%d", i)
		Observe(fp, int64(i), "pkg", "k", nil, map[string]int{"n": 0})
		MarkTried("n", -1)
	}
	if len(TriedIDs("fp0")) != 0 {
		t.Fatalf("el fingerprint más viejo debe haberse evictado")
	}
	last := fmt.Sprintf("fp%d", MaxFingerprints+7)
	if len(TriedIDs(last)) != 1 {
		t.Fatalf("el fingerprint vigente conserva tried")
	}
}
