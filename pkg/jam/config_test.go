package jam

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// v2.3.0: hermeticidad de config en tests (JAV_CONFIG temporal + env limpio).
func isolateConfig(t *testing.T) string {
	t.Helper()
	cfg := filepath.Join(t.TempDir(), "config.json")
	t.Setenv("JAV_CONFIG", cfg)
	t.Setenv("JAV_WS_URL", "")
	t.Setenv("JEV_WS_URL", "")
	t.Setenv("JAV_TOKEN", "")
	t.Setenv("JEV_TOKEN", "")
	t.Setenv("JAV_DEVICE", "")
	t.Setenv("JAV_CERT_FINGERPRINT", "")
	t.Setenv("JEV_CERT_FINGERPRINT", "")
	resetShared()
	t.Cleanup(resetShared)
	return cfg
}

// v2.3.0: un config plano v1.2.x se migra en memoria a `devices.default`
// sin reescribir el archivo.
func TestLoadConfigMigratesFlatV1(t *testing.T) {
	cfg := isolateConfig(t)
	raw := `{"ws_url":"ws://127.0.0.1:38472/","token":"tok-flat",` +
		`"cert_fingerprint":"abc123"}`
	if err := os.WriteFile(cfg, []byte(raw), 0o600); err != nil {
		t.Fatalf("escribir config: %v", err)
	}

	c := LoadConfig()
	if c.ActiveDevice != "default" {
		t.Fatalf("active_device=%q, esperado default", c.ActiveDevice)
	}
	d, ok := c.Devices["default"]
	if !ok {
		t.Fatalf("devices.default ausente: %+v", c.Devices)
	}
	if d.WSURL != "ws://127.0.0.1:38472/" || d.Token != "tok-flat" ||
		d.CertFingerprint != "abc123" {
		t.Fatalf("devices.default mal migrado: %+v", d)
	}
	if c.WSURL != d.WSURL || c.Token != d.Token {
		t.Fatalf("campos raíz no espejan default: %+v", c)
	}
	// La migración es solo en memoria: el disco sigue plano.
	disk, err := os.ReadFile(cfg)
	if err != nil {
		t.Fatalf("leer config: %v", err)
	}
	var rawDisk map[string]any
	if err := json.Unmarshal(disk, &rawDisk); err != nil {
		t.Fatalf("config mutada ilegible: %v", err)
	}
	if _, ok := rawDisk["devices"]; ok {
		t.Fatalf("LoadConfig escribió devices en disco: %s", disk)
	}
}

// v2.3.0: `JAV_DEVICE` elige el dispositivo en caliente sin tocar
// `active_device` en disco; un alias inexistente falla honesto y **nunca**
// deja escapar tráfico al último teléfono.
func TestJavDeviceEnvOverrideAndInvalidFailsHonest(t *testing.T) {
	isolateConfig(t)
	h1 := newWsHarness(t)
	defer h1.srv.Close()
	h2 := newWsHarness(t)
	defer h2.srv.Close()

	if _, err := PairNamed("phone-a", h1.url(), "tok-a"); err != nil {
		t.Fatalf("pair phone-a: %v", err)
	}
	if _, err := PairNamed("phone-b", h2.url(), "tok-b"); err != nil {
		t.Fatalf("pair phone-b: %v", err)
	}
	if ActiveDeviceName() != "phone-b" {
		t.Fatalf("active en disco=%q, esperado phone-b", ActiveDeviceName())
	}

	t.Setenv("JAV_DEVICE", "phone-a")
	resetShared()
	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial con JAV_DEVICE=phone-a: %v", jerr)
	}
	if got := ActiveDeviceName(); got != "phone-a" {
		t.Fatalf("ActiveDeviceName=%q, esperado phone-a (override)", got)
	}
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("call phone-a: %v", jerr)
	}
	if hellos, _, _ := h1.counts(); hellos != 2 {
		t.Fatalf("h1 hellos=%d, esperado 2 (pair + override)", hellos)
	}

	// El archivo no debe cambiar: el override es solo de proceso.
	disk := LoadConfig()
	if disk.ActiveDevice != "phone-b" {
		t.Fatalf("active_device en disco=%q, esperado phone-b (intacto)",
			disk.ActiveDevice)
	}

	// Alias inexistente: VALIDATION_ERROR antes de abrir socket.
	t.Setenv("JAV_DEVICE", "fantasma")
	resetShared()
	before, _, _ := h2.counts()
	if _, jerr := Dial(); jerr == nil || jerr.Code != "VALIDATION_ERROR" {
		t.Fatalf("dial con JAV_DEVICE inexistente: %v (esperado VALIDATION_ERROR)", jerr)
	}
	if after, _, _ := h2.counts(); after != before {
		t.Fatalf("fuga de tráfico: h2 hellos %d→%d con JAV_DEVICE inválido",
			before, after)
	}
	if jerr := ValidateActiveDevice(); jerr == nil ||
		jerr.Code != "VALIDATION_ERROR" {
		t.Fatalf("ValidateActiveDevice=%v, esperado VALIDATION_ERROR", jerr)
	}
}

// v2.3.0: sin `--name`, dos teléfonos con el mismo modelo no se pisan
// (`pixel-9` + `pixel-9-2`); y re-vincular el mismo equipo en otra ruta
// conserva la anterior como FallbackURLs y el Dial cae a ella solo.
func TestPairNamedCollisionAndFallbackURLs(t *testing.T) {
	isolateConfig(t)
	h1 := newWsHarness(t)
	defer h1.srv.Close()
	h2 := newWsHarness(t)
	defer h2.srv.Close()
	for _, h := range []*wsHarness{h1, h2} {
		h.deviceInfo = map[string]any{
			"model": "Pixel 9", "device": "pixel", "manufacturer": "Google",
			"sdk_int": float64(34),
		}
	}

	r1, err := PairNamed("", h1.url(), "tok-1")
	if err != nil {
		t.Fatalf("pair h1 sin alias: %v", err)
	}
	r2, err := PairNamed("", h2.url(), "tok-2")
	if err != nil {
		t.Fatalf("pair h2 sin alias: %v", err)
	}
	if r1.Alias != "pixel-9" || r2.Alias != "pixel-9-2" {
		t.Fatalf("aliases=%q/%q, esperado pixel-9/pixel-9-2", r1.Alias, r2.Alias)
	}
	devs := LoadConfig().Devices
	if len(devs) != 2 {
		t.Fatalf("devices=%v, esperado 2 sin sobrescritura", devs)
	}
	if devs["pixel-9"].WSURL != h1.url() {
		t.Fatalf("pixel-9 pisado: %+v", devs["pixel-9"])
	}
	if devs["pixel-9-2"].WSURL != h2.url() {
		t.Fatalf("pixel-9-2 mal guardado: %+v", devs["pixel-9-2"])
	}

	// Mismo teléfono, dos rutas: la vieja queda como fallback.
	isolateConfig(t)
	if _, err := PairNamed("mi-tel", h1.url(), "tok"); err != nil {
		t.Fatalf("pair mi-tel ruta 1: %v", err)
	}
	if _, err := PairNamed("mi-tel", h2.url(), "tok"); err != nil {
		t.Fatalf("pair mi-tel ruta 2: %v", err)
	}
	e := LoadConfig().Devices["mi-tel"]
	if e.WSURL != h2.url() {
		t.Fatalf("ws_url=%q, esperado la ruta nueva %q", e.WSURL, h2.url())
	}
	found := false
	for _, u := range e.FallbackURLs {
		if u == h1.url() {
			found = true
		}
	}
	if !found {
		t.Fatalf("FallbackURLs=%v, esperado incluir %q", e.FallbackURLs, h1.url())
	}
	if len(e.FallbackURLs) > 4 {
		t.Fatalf("FallbackURLs=%v excede 4", e.FallbackURLs)
	}

	// Ruta primaria caída → failover automático a la anterior.
	resetShared()
	h2.srv.Close()
	before, _, _ := h1.counts()
	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("failover LAN/Tailnet: %v", jerr)
	}
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("call por fallback: %v", jerr)
	}
	if hellos, _, _ := h1.counts(); hellos != before+1 {
		t.Fatalf("h1 hellos=%d, esperado %d (failover)", hellos, before+1)
	}
}

// v2.3.0: eliminar el activo promociona el siguiente (alfabético) y cierra
// la sesión en caliente; el resto de pares se conserva.
func TestRemoveDevicePromotesNext(t *testing.T) {
	isolateConfig(t)
	h1 := newWsHarness(t)
	defer h1.srv.Close()
	h2 := newWsHarness(t)
	defer h2.srv.Close()

	if _, err := PairNamed("phone-a", h1.url(), "tok-a"); err != nil {
		t.Fatalf("pair phone-a: %v", err)
	}
	if _, err := PairNamed("phone-b", h2.url(), "tok-b"); err != nil {
		t.Fatalf("pair phone-b: %v", err)
	}
	if _, jerr := Dial(); jerr != nil {
		t.Fatalf("dial phone-b: %v", jerr)
	}
	_, _, gracefulBefore := h2.counts()

	next, err := RemoveDevice("phone-b")
	if err != nil {
		t.Fatalf("remove phone-b: %v", err)
	}
	if next != "phone-a" {
		t.Fatalf("nuevo activo=%q, esperado phone-a", next)
	}
	if got := ActiveDeviceName(); got != "phone-a" {
		t.Fatalf("ActiveDeviceName=%q, esperado phone-a", got)
	}
	if names := PairedDeviceNames(); len(names) != 1 || names[0] != "phone-a" {
		t.Fatalf("paired=%v, esperado [phone-a]", names)
	}
	c := LoadConfig()
	if c.WSURL != h1.url() {
		t.Fatalf("campos raíz=%q, esperado %q", c.WSURL, h1.url())
	}
	if after := h2.waitGraceful(gracefulBefore + 1); after != gracefulBefore+1 {
		t.Fatalf("sesión previa no cerrada: before=%d after=%d",
			gracefulBefore, after)
	}

	// El activo promocionado responde sin re-vincular.
	if _, jerr := Dial(); jerr != nil {
		t.Fatalf("dial phone-a tras promoción: %v", jerr)
	}

	// Alias desconocido: error con la lista de disponibles.
	if _, err := RemoveDevice("nope"); err == nil {
		t.Fatal("RemoveDevice(\"nope\") debía fallar")
	}
	if _, err := RemoveDevice("phone-a"); err != nil {
		t.Fatalf("remove último dispositivo: %v", err)
	}
	if got := ActiveDeviceName(); got != "" {
		t.Fatalf("active=%q, esperado vacío sin dispositivos", got)
	}
	if c := LoadConfig(); c.WSURL != "" || c.Token != "" {
		t.Fatalf("config sin dispositivo conserva credenciales: %+v", c)
	}
}
