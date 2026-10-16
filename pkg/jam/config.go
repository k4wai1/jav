package jam

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

// Config es la configuración persistente **sin fricción** de Jav
// (`~/.config/jav/config.json`, chmod 0600). Se lee en caliente en cada
// conexión, así que `jav pair` basta: no hay que reiniciar el cliente MCP
// ni exportar variables de entorno.
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
func LoadConfig() Config {
	var c Config
	raw, err := os.ReadFile(ConfigPath())
	if err != nil {
		return Config{}
	}
	_ = json.Unmarshal(raw, &c)
	return c
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
