package jam

import (
	"encoding/binary"
	"testing"
)

// v2.1.0: consulta PTR con QU (respuesta unicast) para `_jav-mcp._tcp.local`.
func TestBuildMDNSQuery(t *testing.T) {
	q := buildMDNSQuery(MDNSServiceType)
	if len(q) < 12+len(MDNSServiceType)+4 {
		t.Fatalf("query corta: %d bytes", len(q))
	}
	if got := binary.BigEndian.Uint16(q[4:6]); got != 1 {
		t.Fatalf("qdcount=%d, esperado 1", got)
	}
	if got := string(q[13 : 13+len("_jav-mcp")]); got != "_jav-mcp" {
		t.Fatalf("primer label=%q", got)
	}
	tail := q[len(q)-4:]
	if binary.BigEndian.Uint16(tail[0:2]) != dnsTypePTR {
		t.Fatalf("qtype=%d, esperado PTR(12)", binary.BigEndian.Uint16(tail[0:2]))
	}
	if tail[2] != 0x80 || tail[3] != 0x01 {
		t.Fatalf("clase=%02x%02x, esperado IN+QU (8001)", tail[2], tail[3])
	}
}

func appendRR(pkt []byte, name string, typ uint16, rdata []byte) []byte {
	pkt = appendDNSName(pkt, name)
	pkt = append(pkt, byte(typ>>8), byte(typ))
	pkt = append(pkt, 0x00, 0x01) // class IN
	pkt = append(pkt, 0, 0, 0, 60)
	pkt = append(pkt, byte(len(rdata)>>8), byte(len(rdata)))
	return append(pkt, rdata...)
}

func srvRData(port int, target string) []byte {
	d := []byte{0, 0, 0, 0, 0, 0} // priority, weight
	binary.BigEndian.PutUint16(d[4:6], uint16(port))
	return appendDNSName(d, target)
}

// v2.1.0: una respuesta mDNS típica (PTR+SRV+A) produce un dispositivo.
func TestCollectMDNSDevice(t *testing.T) {
	pkt := make([]byte, 12)
	binary.BigEndian.PutUint16(pkt[4:6], 0) // qd
	binary.BigEndian.PutUint16(pkt[6:8], 3) // an
	pkt = appendRR(pkt, "_jav-mcp._tcp.local", dnsTypePTR,
		appendDNSName(nil, "Jav-Pixel._jav-mcp._tcp.local"))
	pkt = appendRR(pkt, "Jav-Pixel._jav-mcp._tcp.local", dnsTypeSRV,
		srvRData(38472, "jav-pixel.local"))
	pkt = appendRR(pkt, "jav-pixel.local", dnsTypeA, []byte{192, 168, 1, 40})

	srv := map[string]mdnsSRV{}
	a := map[string]string{}
	if err := collectMDNS(pkt, srv, a); err != nil {
		t.Fatalf("collectMDNS: %v", err)
	}
	devs := devicesFromRecords(srv, a)
	if len(devs) != 1 {
		t.Fatalf("devices=%v, esperado 1", devs)
	}
	d := devs[0]
	if d.IP != "192.168.1.40" || d.Port != 38472 || d.Name != "jav-pixel" {
		t.Fatalf("device=%+v", d)
	}
}

// Un SRV de otro servicio (o sin A) no debe inventar dispositivos.
func TestCollectMDNSIgnoresForeignAndUnresolved(t *testing.T) {
	pkt := make([]byte, 12)
	binary.BigEndian.PutUint16(pkt[6:8], 2)
	pkt = appendRR(pkt, "_other._tcp.local", dnsTypeSRV, srvRData(9999, "x.local"))
	pkt = appendRR(pkt, "Jav-SinA._jav-mcp._tcp.local", dnsTypeSRV,
		srvRData(38472, "sin-a.local"))

	srv := map[string]mdnsSRV{}
	a := map[string]string{}
	if err := collectMDNS(pkt, srv, a); err != nil {
		t.Fatalf("collectMDNS: %v", err)
	}
	if devs := devicesFromRecords(srv, a); len(devs) != 0 {
		t.Fatalf("devices=%v, esperado 0", devs)
	}
}

// Compresión de nombres (puntero 0xC0) en el target de SRV.
func TestReadDNSNameWithPointer(t *testing.T) {
	pkt := appendDNSName(nil, "jav-pixel.local")
	pkt = append(pkt, 0xC0, 0x00) // puntero al offset 0
	name, next, err := readDNSName(pkt, len(pkt)-2)
	if err != nil {
		t.Fatalf("readDNSName: %v", err)
	}
	if name != "jav-pixel.local" {
		t.Fatalf("name=%q", name)
	}
	if next != len(pkt) {
		t.Fatalf("next=%d, esperado %d", next, len(pkt))
	}
}

// Paquete truncado → error (nunca pánico).
func TestParseMDNSTruncated(t *testing.T) {
	if _, err := parseMDNSRecords([]byte{0, 0, 0}); err == nil {
		t.Fatal("paquete corto debe fallar")
	}
	pkt := make([]byte, 12)
	binary.BigEndian.PutUint16(pkt[6:8], 1)
	if _, err := parseMDNSRecords(pkt); err == nil {
		t.Fatal("anuncio sin RR debe fallar")
	}
}
