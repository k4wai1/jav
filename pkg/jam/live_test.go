package jam

import (
	"os"
	"testing"
)

// Live Fase 2b: hello (token migrado a AndroidKeyStore sigue válido) +
// get_audit contra el dispositivo real. Requiere `adb forward` y `.env`.
func TestLiveHelloAudit(t *testing.T) {
	if os.Getenv("JEV_LIVE") != "1" {
		t.Skip("set JEV_LIVE=1 (requiere dispositivo + adb forward)")
	}
	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial/hello: %v", jerr)
	}
	defer c.Close()
	t.Logf("hello ok url=%s app=%s scopes=%v", c.URL, c.AppVersion, c.Scopes)
	aud, jerr := c.GetAudit(5, 0)
	if jerr != nil {
		t.Fatalf("get_audit: %v", jerr)
	}
	t.Logf("get_audit ok total=%v returned=%v", aud["total_buffered"], aud["returned"])
}
