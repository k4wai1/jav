package jam

import (
	"encoding/binary"
	"errors"
	"net"
	"sort"
	"strings"
	"time"
)

// v2.1.0: descubrimiento mDNS ligero para `jav pair` (sin dependencias).
// Consulta `_jav-mcp._tcp.local` por multicast (QU: respuesta unicast),
// parsea PTR/SRV/A y devuelve los dispositivos con su IP y puerto.
// Ventana por defecto ~800 ms: suficiente en LAN y no bloquea la CLI.

// MDNSServiceType tipo DNS-SD que anuncia la app (NsdManager).
const MDNSServiceType = "_jav-mcp._tcp.local."

// DefaultMDNSTimeout ventana de escucha de `jav pair` (corta a propósito).
const DefaultMDNSTimeout = 800 * time.Millisecond

const mdnsGroup = "224.0.0.251:5353"

const (
	dnsTypeA   = 1
	dnsTypePTR = 12
	dnsTypeSRV = 33
)

// MDNSDevice teléfono descubierto en la LAN.
type MDNSDevice struct {
	Name string
	IP   string
	Port int
}

type mdnsSRV struct {
	target string
	port   int
}

var (
	errDNSName     = errors.New("mDNS: nombre inválido")
	errDNSOverflow = errors.New("mDNS: paquete truncado")
)

// appendDNSName codifica un nombre DNS (`a.b.c` / `a.b.c.`) en labels.
func appendDNSName(buf []byte, name string) []byte {
	n := strings.TrimSuffix(name, ".")
	if n == "" {
		return append(buf, 0)
	}
	for _, label := range strings.Split(n, ".") {
		if label == "" || len(label) > 63 {
			continue
		}
		buf = append(buf, byte(len(label)))
		buf = append(buf, label...)
	}
	return append(buf, 0)
}

// readDNSName lee un nombre (con punteros de compresión) y devuelve el
// nombre normalizado (minúsculas, sin punto final) y el offset siguiente.
func readDNSName(pkt []byte, off int) (string, int, error) {
	labels := make([]string, 0, 4)
	pos := off
	next := -1
	jumps := 0
	for {
		if pos < 0 || pos >= len(pkt) {
			return "", 0, errDNSOverflow
		}
		l := int(pkt[pos])
		switch {
		case l == 0:
			pos++
			if next < 0 {
				next = pos
			}
			return strings.ToLower(strings.Join(labels, ".")), next, nil
		case l&0xC0 == 0xC0:
			if pos+1 >= len(pkt) {
				return "", 0, errDNSOverflow
			}
			ptr := int(binary.BigEndian.Uint16(pkt[pos:pos+2]) & 0x3FFF)
			if next < 0 {
				next = pos + 2
			}
			jumps++
			if jumps > 64 || ptr >= len(pkt) {
				return "", 0, errDNSName
			}
			pos = ptr
		case l&0xC0 != 0:
			return "", 0, errDNSName
		default:
			if pos+1+l > len(pkt) {
				return "", 0, errDNSOverflow
			}
			labels = append(labels, string(pkt[pos+1:pos+1+l]))
			pos += 1 + l
		}
	}
}

// buildMDNSQuery arma la consulta PTR con el bit QU (respuesta unicast).
func buildMDNSQuery(service string) []byte {
	pkt := make([]byte, 12, 64)
	binary.BigEndian.PutUint16(pkt[4:6], 1) // qdcount=1
	pkt = appendDNSName(pkt, service)
	pkt = append(pkt, 0, dnsTypePTR)
	pkt = append(pkt, 0x80, 0x01) // IN + QU
	return pkt
}

type mdnsRecord struct {
	name     string
	typ      uint16
	rdataOff int
	rdlen    int
}

// parseMDNSRecords extrae los RR (answers+authority+additional).
func parseMDNSRecords(pkt []byte) ([]mdnsRecord, error) {
	if len(pkt) < 12 {
		return nil, errDNSOverflow
	}
	qd := int(binary.BigEndian.Uint16(pkt[4:6]))
	an := int(binary.BigEndian.Uint16(pkt[6:8]))
	ns := int(binary.BigEndian.Uint16(pkt[8:10]))
	ar := int(binary.BigEndian.Uint16(pkt[10:12]))
	off := 12
	for i := 0; i < qd; i++ {
		_, next, err := readDNSName(pkt, off)
		if err != nil {
			return nil, err
		}
		if next+4 > len(pkt) {
			return nil, errDNSOverflow
		}
		off = next + 4
	}
	recs := make([]mdnsRecord, 0, an+ns+ar)
	for i := 0; i < an+ns+ar; i++ {
		name, next, err := readDNSName(pkt, off)
		if err != nil {
			return recs, err
		}
		if next+10 > len(pkt) {
			return recs, errDNSOverflow
		}
		typ := binary.BigEndian.Uint16(pkt[next : next+2])
		rdlen := int(binary.BigEndian.Uint16(pkt[next+8 : next+10]))
		rdata := next + 10
		if rdata+rdlen > len(pkt) {
			return recs, errDNSOverflow
		}
		recs = append(recs, mdnsRecord{name: name, typ: typ, rdataOff: rdata, rdlen: rdlen})
		off = rdata + rdlen
	}
	return recs, nil
}

// collectMDNS acumula SRV y A de un paquete en los mapas del llamante.
func collectMDNS(pkt []byte, srv map[string]mdnsSRV, a map[string]string) error {
	recs, err := parseMDNSRecords(pkt)
	for _, r := range recs {
		switch r.typ {
		case dnsTypeSRV:
			if r.rdlen < 7 {
				continue
			}
			port := int(binary.BigEndian.Uint16(pkt[r.rdataOff+4 : r.rdataOff+6]))
			target, _, terr := readDNSName(pkt, r.rdataOff+6)
			if terr != nil || target == "" || port <= 0 {
				continue
			}
			srv[r.name] = mdnsSRV{target: target, port: port}
		case dnsTypeA:
			if r.rdlen != 4 {
				continue
			}
			ip := net.IPv4(pkt[r.rdataOff], pkt[r.rdataOff+1],
				pkt[r.rdataOff+2], pkt[r.rdataOff+3]).String()
			a[r.name] = ip
		}
	}
	return err
}

// devicesFromRecords empareja SRV(instance)→target con A(target)→IP.
func devicesFromRecords(srv map[string]mdnsSRV, a map[string]string) []MDNSDevice {
	base := strings.TrimSuffix(strings.ToLower(MDNSServiceType), ".")
	seen := map[string]bool{}
	out := make([]MDNSDevice, 0, len(srv))
	for name, s := range srv {
		if !strings.HasSuffix(name, "."+base) {
			continue
		}
		ip := a[s.target]
		if ip == "" || ip == "<nil>" || ip == "0.0.0.0" {
			continue
		}
		key := ip + ":" + strconvItoa(s.port)
		if seen[key] {
			continue
		}
		seen[key] = true
		label := strings.TrimSuffix(name, "."+base)
		out = append(out, MDNSDevice{Name: label, IP: ip, Port: s.port})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].IP == out[j].IP {
			return out[i].Port < out[j].Port
		}
		return out[i].IP < out[j].IP
	})
	return out
}

func strconvItoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [8]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}

// DiscoverMDNS busca dispositivos Jav en la LAN (ventana corta). Nunca
// escribe a stdout; sin red/multicast devuelve lista vacía.
func DiscoverMDNS(timeout time.Duration) []MDNSDevice {
	if timeout <= 0 {
		timeout = DefaultMDNSTimeout
	}
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		return nil
	}
	defer conn.Close()
	dst, err := net.ResolveUDPAddr("udp4", mdnsGroup)
	if err != nil {
		return nil
	}
	_ = conn.SetWriteDeadline(time.Now().Add(timeout))
	if _, err := conn.WriteToUDP(buildMDNSQuery(MDNSServiceType), dst); err != nil {
		return nil
	}
	srv := map[string]mdnsSRV{}
	a := map[string]string{}
	deadline := time.Now().Add(timeout)
	buf := make([]byte, 9000)
	for {
		_ = conn.SetReadDeadline(deadline)
		n, _, rerr := conn.ReadFromUDP(buf)
		if rerr != nil {
			break
		}
		_ = collectMDNS(buf[:n], srv, a)
	}
	return devicesFromRecords(srv, a)
}
