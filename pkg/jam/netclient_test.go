package jam

import "testing"

// v2.0.0: el cliente HTTP de IA debe existir siempre (S1/S2 lo usan como
// default) y llevar Transport propio (no el DefaultTransport global).
func TestHTTPClientInitialized(t *testing.T) {
	if HTTPClient == nil {
		t.Fatal("HTTPClient nil")
	}
	if HTTPClient.Transport == nil {
		t.Fatal("HTTPClient.Transport nil (se espera *http.Transport con resolver)")
	}
}

// v2.0.0: dentro de Termux (TERMUX_VERSION) se activa el resolver DNS
// explícito sin depender de `/etc/resolv.conf`.
func TestNeedsExplicitDNSInTermux(t *testing.T) {
	t.Setenv("TERMUX_VERSION", "0.118.0")
	if !isAndroidOrTermux() {
		t.Fatal("isAndroidOrTermux() false con TERMUX_VERSION definido")
	}
	if !needsExplicitDNS() {
		t.Fatal("needsExplicitDNS() false en Termux")
	}
}

// v2.0.0: PREFIX=.../com.termux/... también identifica Termux.
func TestIsAndroidOrTermuxByPrefix(t *testing.T) {
	t.Setenv("TERMUX_VERSION", "")
	t.Setenv("PREFIX", "/data/data/com.termux/files/usr")
	if !isAndroidOrTermux() {
		t.Fatal("isAndroidOrTermux() false con PREFIX de com.termux")
	}
}
