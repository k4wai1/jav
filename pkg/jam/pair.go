package jam

import (
	"fmt"
	"strings"
)

// PairResult resume una vinculación `jav pair` para imprimir en terminal.
type PairResult struct {
	Alias        string
	URL          string
	Fingerprint  string
	Manufacturer string
	Model        string
	Device       string
	SDK          int
}

// NormalizeAddr convierte una IP/host/alias en la URL WS/WSS de Jav:
//   - `wss://…`/`ws://…` → tal cual;
//   - `usb`/`loopback`/`local`/`127.0.0.1`/`localhost` → `ws://127.0.0.1:38472/`;
//   - cualquier otra IP/host (p.ej. Tailnet `100.x.y.z`) → `wss://<host>:38472/`.
func NormalizeAddr(raw string) string {
	s := strings.TrimSpace(raw)
	if s == "" {
		return s
	}
	low := strings.ToLower(s)
	if strings.HasPrefix(low, "ws://") || strings.HasPrefix(low, "wss://") {
		return s
	}
	switch low {
	case "usb", "loopback", "local":
		return "ws://127.0.0.1:38472/"
	}
	if isLoopbackHost(s) {
		if strings.Contains(s, ":") {
			return "ws://" + s + "/"
		}
		return "ws://" + s + ":38472/"
	}
	if strings.Contains(s, ":") {
		return "wss://" + s + "/"
	}
	return "wss://" + s + ":38472/"
}

func isLoopbackHost(s string) bool {
	return s == "127.0.0.1" || s == "localhost" || strings.HasPrefix(s, "127.")
}

// Pair vincula con el alias derivado del modelo (v2.2.0 delega en PairNamed).
func Pair(rawAddr, token string) (PairResult, error) {
	return PairNamed("", rawAddr, token)
}

// PairNamed vincula un teléfono bajo un alias (v2.2.0). Con `alias` vacío
// se deriva de `model`/`device` sanitizado. Persiste el `DeviceEntry`, deja
// ese alias como activo y resetea la sesión en caliente.
func PairNamed(alias, rawAddr, token string) (PairResult, error) {
	url := NormalizeAddr(rawAddr)
	if strings.TrimSpace(token) == "" {
		return PairResult{}, fmt.Errorf("falta el token de la app (tarjeta 3 → COPIA)")
	}
	// fp="" fuerza TOFU: dialConn captura el SHA-256 presentado por el teléfono.
	c, captured, jerr := dialConn(url, token, "")
	if jerr != nil {
		return PairResult{}, fmt.Errorf("%s: %s", jerr.Code, jerr.Message)
	}
	// El `hello` ya pasó: leemos metadatos (para alias/modelo) antes de
	// persistir; si `get_device_info` falla, vinculamos igual.
	res := PairResult{URL: url, Fingerprint: captured}
	if info, jerr := c.callOnConn("get_device_info", nil, 0); jerr == nil {
		res.Manufacturer = asString(info["manufacturer"])
		res.Model = asString(info["model"])
		res.Device = asString(info["device"])
		res.SDK = asInt(info["sdk_int"])
	}
	c.closeConn()

	// Alias: explícito, reutilización por fingerprint (mismo teléfono en
	// otra ruta) o colisión `base-N` si el alias base ya es otro teléfono.
	if strings.TrimSpace(alias) == "" {
		base := SanitizeAlias(firstNonEmpty(res.Model, res.Device, "default"))
		existing := LoadConfig().Devices
		res.Alias = base
		if captured != "" {
			for k, d := range existing {
				if d.CertFingerprint != "" && d.CertFingerprint == captured {
					res.Alias = k
					break
				}
			}
		}
		if res.Alias == base {
			if d, ok := existing[base]; ok && !sameDeviceEntry(d, captured, url) {
				for i := 2; ; i++ {
					cand := fmt.Sprintf("%s-%d", base, i)
					if _, taken := existing[cand]; !taken {
						res.Alias = cand
						break
					}
				}
			}
		}
	} else {
		res.Alias = SanitizeAlias(alias)
	}
	if err := UpdateConfig(func(cf *Config) {
		cf.WSURL = url
		cf.Token = token
		cf.CertFingerprint = captured
		cf.ActiveDevice = res.Alias
		if cf.Devices == nil {
			cf.Devices = map[string]DeviceEntry{}
		}
		entry := DeviceEntry{
			WSURL:           url,
			Token:           token,
			CertFingerprint: captured,
			Manufacturer:    res.Manufacturer,
			Model:           res.Model,
			Device:          res.Device,
			SDK:             res.SDK,
		}
		// Failover: mismo teléfono visto en otra ruta (Tailnet ↔ LAN).
		// La ruta anterior (y sus fallbacks) se conserva sin duplicados.
		if prev, ok := cf.Devices[res.Alias]; ok && prev.CertFingerprint == captured {
			fb := make([]string, 0, 5)
			add := func(u string) {
				u = strings.TrimSpace(u)
				if u == "" || u == url || len(fb) >= 4 {
					return
				}
				for _, x := range fb {
					if x == u {
						return
					}
				}
				fb = append(fb, u)
			}
			add(prev.WSURL)
			for _, u := range prev.FallbackURLs {
				add(u)
			}
			for _, u := range entry.FallbackURLs {
				add(u)
			}
			if len(fb) > 0 {
				entry.FallbackURLs = fb
			}
		}
		cf.Devices[res.Alias] = entry
	}); err != nil {
		return PairResult{}, fmt.Errorf("no pude escribir %s: %w", ConfigPath(), err)
	}
	ResetSessionState()
	return res, nil
}

// sameDeviceEntry decide si una entrada ya guardada es el mismo teléfono:
// mismo pin cuando ambos lo tienen; sin pin (ws:// o TOFU pendiente), misma
// ruta. Así re-vincular el mismo equipo en otra ruta reutiliza el alias en
// vez de crear `pixel-9-2`.
func sameDeviceEntry(d DeviceEntry, captured, url string) bool {
	if captured != "" && d.CertFingerprint != "" {
		return d.CertFingerprint == captured
	}
	return d.CertFingerprint == captured &&
		strings.TrimSpace(d.WSURL) == strings.TrimSpace(url)
}

func asString(v any) string {
	s, _ := v.(string)
	return s
}

func asInt(v any) int {
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case int64:
		return int(n)
	}
	return 0
}
