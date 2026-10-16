package jam

import (
	"fmt"
	"strings"
)

// PairResult resume una vinculación `jav pair` para imprimir en terminal.
type PairResult struct {
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

// Pair vincula este binario con un teléfono en un paso: conecta (hello),
// hace **Auto-TOFU** del certificado en `wss://`, lee `get_device_info` y
// persiste `~/.config/jav/config.json` (0600). No requiere reiniciar el
// cliente MCP: la config se relee en caliente en cada conexión.
//
// El pin previo se ignora al vincular (TOFU limpio) y se reemplaza por el
// fingerprint observado en esta conexión.
func Pair(rawAddr, token string) (PairResult, error) {
	url := NormalizeAddr(rawAddr)
	if strings.TrimSpace(token) == "" {
		return PairResult{}, fmt.Errorf("falta el token de la app (tarjeta 3 → COPIA)")
	}
	// fp="" fuerza TOFU: dialConn captura el SHA-256 presentado por el teléfono.
	c, captured, jerr := dialConn(url, token, "")
	if jerr != nil {
		return PairResult{}, fmt.Errorf("%s: %s", jerr.Code, jerr.Message)
	}
	// El `hello` ya pasó: persistimos la vinculación aunque `get_device_info`
	// falle (la conexión quedó probada y el pin TOFU fijado).
	if err := UpdateConfig(func(cf *Config) {
		cf.WSURL = url
		cf.Token = token
		cf.CertFingerprint = captured
	}); err != nil {
		c.closeConn()
		return PairResult{}, fmt.Errorf("no pude escribir %s: %w", ConfigPath(), err)
	}
	res := PairResult{URL: url, Fingerprint: captured}
	if info, jerr := c.callOnConn("get_device_info", nil, 0); jerr == nil {
		res.Manufacturer = asString(info["manufacturer"])
		res.Model = asString(info["model"])
		res.Device = asString(info["device"])
		res.SDK = asInt(info["sdk_int"])
	}
	c.closeConn()
	return res, nil
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
