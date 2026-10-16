package jam

import (
	"os"
	"path/filepath"
	"testing"
)

// TestMain aísla la config real: apunta JAV_CONFIG a un archivo temporal
// para que los tests sean herméticos (no leen/escriben ~/.config/jav).
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "jav-cfg-test")
	if err == nil {
		_ = os.Setenv("JAV_CONFIG", filepath.Join(dir, "config.json"))
	}
	code := m.Run()
	if err == nil {
		_ = os.RemoveAll(dir)
	}
	os.Exit(code)
}
