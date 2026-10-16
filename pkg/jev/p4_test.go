package jev

import (
	"strings"
	"testing"
)

func TestSerialTableMarksTried(t *testing.T) {
	table := []SerialRow{
		{0, "Button", "top-left", "click", "a"},
		{1, "Button", "top-right", "click", "b"},
	}
	got := serialTable(table, map[int]bool{1: true})
	if strings.Contains(got[0][3].(string), "tried") {
		t.Fatalf("fila no probada sin tried: %v", got[0][3])
	}
	if !strings.Contains(got[1][3].(string), "tried") {
		t.Fatalf("fila probada con tried: %v", got[1][3])
	}
	if table[1][3] != "click" {
		t.Fatalf("no debe mutar la entrada: %v", table)
	}
}

func TestSerialTableWithoutTriedUnchanged(t *testing.T) {
	table := []SerialRow{{0, "Button", "top-left", "click", "a"}}
	got := serialTable(table, nil)
	if got[0][3] != "click" {
		t.Fatalf("sin triedIdx no debe marcarse: %v", got[0][3])
	}
}
