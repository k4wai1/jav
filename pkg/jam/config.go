package jam

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// DeviceEntry es un teléfono vinculado (v2.2.0): sus credenciales y
// metadatos de `get_device_info` para el mapa multidispositivo.
type DeviceEntry struct {
	WSURL           string   `json:"ws_url"`
	Token           string   `json:"token"`
	CertFingerprint string   `json:"cert_fingerprint,omitempty"`
	Manufacturer    string   `json:"manufacturer,omitempty"`
	Model           string   `json:"model,omitempty"`
	Device          string   `json:"device,omitempty"`
	SDK             int      `json:"sdk,omitempty"`
	FallbackURLs    []string `json:"fallback_urls,omitempty"`
}

// Config es la configuración persistente **sin fricción** de Jav
// (`~/.config/jav/config.json`, chmod 0600). Se lee en caliente en cada
// conexión, así que `jav pair` basta: no hay que reiniciar el cliente MCP
// ni exportar variables de entorno.
//
// v2.2.0: multidispositivo. Los campos raíz (`ws_url`/`token`/`cert_fingerprint`)
// se conservan como espejo del dispositivo activo (compat v1.2.x) y `devices`
// guarda todos los pares; `active_device` (o `JAV_DEVICE`) elige cuál.
//
// Prioridad de lectura por campo: variable de entorno → config.json →
// default (v1.2.1).
type Config struct {
	WSURL            string `json:"ws_url,omitempty"`
	Token            string `json:"token,omitempty"`
	CertFingerprint  string `json:"cert_fingerprint,omitempty"`
	OpenRouterAPIKey string `json:"openrouter_api_key,omitempty"`
	AIBaseURL        string `json:"ai_base_url,omitempty"`
	AIAPIKey         string `json:"ai_api_key,omitempty"`
	AIModel          string `json:"ai_model,omitempty"`

	ActiveDevice string                 `json:"active_device,omitempty"`
	Devices      map[string]DeviceEntry `json:"devices,omitempty"`
}

// ConfigPath resuelve el archivo de configuración. Override `JAV_CONFIG`
// (tests/portabilidad); por defecto `~/.config/jav/config.json`
// (os.UserConfigDir respeta XDG_CONFIG_HOME).
func ConfigPath() string {
	if p := strings.TrimSpace(os.Getenv("JAV_CONFIG")); p != "" {
		return p
	}
	dir, err := os.UserConfigDir()
	if err != nil || dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, ".config")
	}
	return filepath.Join(dir, "jav", "config.json")
}

// LoadConfig lee el archivo; ausencia o error → Config vacío (nunca cuelga,
// nunca inventa). El JSON inválido se ignora y se devuelve lo leído.
//
// v2.2.0: normaliza devices en memoria (migración v1.2.x → "default") y
// aplica el dispositivo activo (`JAV_DEVICE` → `active_device`) sobre los
// campos raíz, sin escribir en disco.
func LoadConfig() Config {
	var c Config
	raw, err := os.ReadFile(ConfigPath())
	if err != nil {
		return Config{}
	}
	_ = json.Unmarshal(raw, &c)
	normalizeDevices(&c)
	return c
}

// normalizeDevices migra configs planas (v1.2.x) y resuelve el alias activo
// en memoria: los campos raíz pasan a reflejar el dispositivo elegido.
//
// v2.3.0: si `JAV_DEVICE` apunta a un alias inexistente, los campos raíz se
// limpian (fail-closed): nunca se reutiliza el último teléfono por accidente.
func normalizeDevices(c *Config) {
	if c.Devices == nil {
		c.Devices = map[string]DeviceEntry{}
	}
	if len(c.Devices) == 0 && (c.WSURL != "" || c.Token != "") {
		c.Devices["default"] = DeviceEntry{
			WSURL:           c.WSURL,
			Token:           c.Token,
			CertFingerprint: c.CertFingerprint,
		}
		if c.ActiveDevice == "" {
			c.ActiveDevice = "default"
		}
	}
	if env := strings.TrimSpace(os.Getenv("JAV_DEVICE")); env != "" {
		if key := findDeviceKey(c.Devices, env); key != "" {
			d := c.Devices[key]
			c.WSURL = d.WSURL
			c.Token = d.Token
			c.CertFingerprint = d.CertFingerprint
		} else {
			c.WSURL = ""
			c.Token = ""
			c.CertFingerprint = ""
		}
		return
	}
	if c.ActiveDevice != "" {
		if d, ok := c.Devices[c.ActiveDevice]; ok {
			c.WSURL = d.WSURL
			c.Token = d.Token
			c.CertFingerprint = d.CertFingerprint
		}
	}
}

// wsEnvFixed indica que el operador fijó la URL por entorno (sin failover).
func wsEnvFixed() bool {
	return strings.TrimSpace(os.Getenv("JAV_WS_URL")) != "" ||
		strings.TrimSpace(os.Getenv("JEV_WS_URL")) != ""
}

// findDeviceKey busca un alias exacto o saneado; "" si no existe.
func findDeviceKey(devs map[string]DeviceEntry, want string) string {
	want = strings.TrimSpace(want)
	if want == "" {
		return ""
	}
	if _, ok := devs[want]; ok {
		return want
	}
	if norm := SanitizeAlias(want); norm != want {
		if _, ok := devs[norm]; ok {
			return norm
		}
	}
	return ""
}

// SaveConfig escribe el archivo de forma atómica con permisos 0600
// (directorio 0700). El token vive en claro en disco con 0600 (igual que
// `.env`); en el teléfono sigue cifrado en el AndroidKeyStore.
func SaveConfig(c Config) error {
	p := ConfigPath()
	if dir := filepath.Dir(p); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return err
		}
	}
	raw, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	tmp := p + ".tmp"
	if err := os.WriteFile(tmp, append(raw, '\n'), 0o600); err != nil {
		return err
	}
	if err := os.Chmod(tmp, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, p)
}

// UpdateConfig carga, aplica fn y guarda: preserva los campos no tocados
// (p.ej. Auto-TOFU solo cambia cert_fingerprint).
func UpdateConfig(fn func(*Config)) error {
	c := LoadConfig()
	fn(&c)
	return SaveConfig(c)
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}

// normalizeFP normaliza el pin SHA-256 (minúsculas, sin `:` ni espacios).
func normalizeFP(v string) string {
	v = strings.ToLower(strings.TrimSpace(v))
	v = strings.ReplaceAll(v, ":", "")
	v = strings.ReplaceAll(v, " ", "")
	return v
}

// --- Accesores de IA (S1/S2) sin fricción: env → config.json ------------

// OpenRouterAPIKey: OPENROUTER_API_KEY → config.openrouter_api_key.
func OpenRouterAPIKey() string {
	return firstNonEmpty(os.Getenv("OPENROUTER_API_KEY"), LoadConfig().OpenRouterAPIKey)
}

// AIModel: JEV_MODEL → config.ai_model.
func AIModel() string {
	return firstNonEmpty(os.Getenv("JEV_MODEL"), LoadConfig().AIModel)
}

// AIBaseURL: JAV_AI_BASE_URL → config.ai_base_url.
func AIBaseURL() string {
	return firstNonEmpty(os.Getenv("JAV_AI_BASE_URL"), LoadConfig().AIBaseURL)
}

// AIAPIKey: JAV_AI_API_KEY → config.ai_api_key (key agnóstica de S2).
func AIAPIKey() string {
	return firstNonEmpty(os.Getenv("JAV_AI_API_KEY"), LoadConfig().AIAPIKey)
}

// --- Multidispositivo (v2.2.0) -----------------------------------------

// ActiveDeviceName alias vigente: `JAV_DEVICE` → config.active_device.
func ActiveDeviceName() string {
	if v := strings.TrimSpace(os.Getenv("JAV_DEVICE")); v != "" {
		return v
	}
	return LoadConfig().ActiveDevice
}

// PairedDevices mapa alias → dispositivo vinculado.
func PairedDevices() map[string]DeviceEntry {
	return LoadConfig().Devices
}

// PairedDeviceNames alias ordenados alfabéticamente.
func PairedDeviceNames() []string {
	devs := PairedDevices()
	names := make([]string, 0, len(devs))
	for n := range devs {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}

var aliasRe = regexp.MustCompile(`[^a-z0-9._-]+`)

// SanitizeAlias normaliza un alias para usarlo como clave estable:
// minúsculas, `[^a-z0-9._-]+` → "-", sin "-" en extremos; vacío → "default".
func SanitizeAlias(raw string) string {
	s := aliasRe.ReplaceAllString(strings.ToLower(strings.TrimSpace(raw)), "-")
	s = strings.Trim(s, "-")
	if s == "" {
		return "default"
	}
	return s
}

// SelectDevice cambia el dispositivo activo (hot switch): persiste
// `active_device`, sincroniza los campos raíz, resetea la sesión WS y la
// caché del cliente (OnDeviceSwitch). El alias puede ir exacto o
// sanitizado. Si no existe, error con la lista de vinculados.
func SelectDevice(alias string) (DeviceEntry, error) {
	want := strings.TrimSpace(alias)
	if want == "" {
		return DeviceEntry{}, fmt.Errorf("alias vacío; dispositivos vinculados: %s", devicesLabel())
	}
	c := LoadConfig()
	key := findDeviceKey(c.Devices, want)
	if key == "" {
		return DeviceEntry{}, fmt.Errorf(
			"dispositivo %q no vinculado; disponibles: %s", want, devicesLabel())
	}
	d := c.Devices[key]
	c.ActiveDevice = key
	c.WSURL = d.WSURL
	c.Token = d.Token
	c.CertFingerprint = d.CertFingerprint
	if err := SaveConfig(c); err != nil {
		return DeviceEntry{}, fmt.Errorf("no pude escribir %s: %w", ConfigPath(), err)
	}
	ResetSessionState()
	return d, nil
}

// ValidateActiveDevice comprueba que `JAV_DEVICE` (si está definido) apunte
// a un dispositivo vinculado. Sin la variable siempre es válido.
func ValidateActiveDevice() *JamError {
	env := strings.TrimSpace(os.Getenv("JAV_DEVICE"))
	if env == "" {
		return nil
	}
	if findDeviceKey(LoadConfig().Devices, env) != "" {
		return nil
	}
	return &JamError{Code: "VALIDATION_ERROR", Message: fmt.Sprintf(
		"JAV_DEVICE=%q no está vinculado; disponibles: %s", env, devicesLabel())}
}

// ActiveDeviceFallbackURLs rutas alternativas del dispositivo activo. Vacío
// si `JAV_WS_URL`/`JEV_WS_URL` fijan URL (el operador manda).
func ActiveDeviceFallbackURLs() []string {
	if wsEnvFixed() {
		return nil
	}
	c := LoadConfig()
	key := c.ActiveDevice
	if env := strings.TrimSpace(os.Getenv("JAV_DEVICE")); env != "" {
		key = findDeviceKey(c.Devices, env)
	}
	if key == "" {
		return nil
	}
	fb := c.Devices[key].FallbackURLs
	out := make([]string, len(fb))
	copy(out, fb)
	return out
}

// RemoveDevice desvincula un alias. Si era el activo, promociona el primero
// restante (orden alfabético) o deja la config sin dispositivo. Cierra la
// sesión en caliente.
func RemoveDevice(alias string) (newActive string, err error) {
	want := strings.TrimSpace(alias)
	c := LoadConfig()
	key := findDeviceKey(c.Devices, want)
	if key == "" {
		if want == "" {
			want = "(vacío)"
		}
		return "", fmt.Errorf("dispositivo %q no vinculado; disponibles: %s", want, devicesLabel())
	}
	delete(c.Devices, key)
	if c.ActiveDevice == key {
		names := make([]string, 0, len(c.Devices))
		for n := range c.Devices {
			names = append(names, n)
		}
		sort.Strings(names)
		if len(names) == 0 {
			c.ActiveDevice = ""
			c.WSURL = ""
			c.Token = ""
			c.CertFingerprint = ""
		} else {
			next := names[0]
			c.ActiveDevice = next
			d := c.Devices[next]
			c.WSURL = d.WSURL
			c.Token = d.Token
			c.CertFingerprint = d.CertFingerprint
		}
	}
	if err := SaveConfig(c); err != nil {
		return "", fmt.Errorf("no pude escribir %s: %w", ConfigPath(), err)
	}
	ResetSessionState()
	return c.ActiveDevice, nil
}

// devicesLabel lista legible para errores ("a, b" o "(ninguno)").
func devicesLabel() string {
	names := PairedDeviceNames()
	if len(names) == 0 {
		return "(ninguno)"
	}
	return strings.Join(names, ", ")
}
