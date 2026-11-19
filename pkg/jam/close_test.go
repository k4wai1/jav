package jam

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// wsHarness es un servidor WS de prueba single-client que cuenta
// conexiones, `hello`s y cierres ordenados, y puede tirar la conexión.
type wsHarness struct {
	t             *testing.T
	srv           *httptest.Server
	mu            sync.Mutex
	hellos        int
	conns         int
	gracefulClose int
	forceClose    chan struct{}
	rejectHello   bool
	// v1.2.5: caps opcionales en el hello (nil = app <1.2.5 sin caps).
	helloCaps map[string]any
	// v2.3.0: metadatos de `get_device_info` (modelo → alias automático).
	deviceInfo map[string]any
	// v2.3.1: evento asíncrono a intercalar ANTES de la respuesta.
	preEvent map[string]any
	// v2.4.0: resultado de `get_caps` (nil = app <2.4.0 → METHOD_NOT_ALLOWED).
	capsResult map[string]any
	// v2.4.0: simula una APK <2.4.0 que rechaza `get_caps`.
	rejectCaps bool
}

func newWsHarness(t *testing.T) *wsHarness {
	h := &wsHarness{t: t, forceClose: make(chan struct{}, 16)}
	up := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	h.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		h.mu.Lock()
		h.conns++
		h.mu.Unlock()
		defer conn.Close()

		stop := make(chan struct{})
		go func() {
			select {
			case <-h.forceClose:
				_ = conn.Close()
			case <-stop:
			}
		}()
		defer close(stop)

		for {
			_, data, err := conn.ReadMessage()
			if err != nil {
				if ce, ok := err.(*websocket.CloseError); ok &&
					ce.Code == websocket.CloseNormalClosure {
					h.mu.Lock()
					h.gracefulClose++
					h.mu.Unlock()
				}
				return
			}
			var req map[string]any
			_ = json.Unmarshal(data, &req)
			id := req["id"]
			method, _ := req["method"].(string)
			if method == "hello" {
				h.mu.Lock()
				h.hellos++
				reject := h.rejectHello
				caps := h.helloCaps
				h.mu.Unlock()
				if reject {
					_ = conn.WriteJSON(map[string]any{
						"jsonrpc": "2.0", "id": id, "ok": false,
						"code": "UNAUTHORIZED", "error": "token inválido",
					})
					continue
				}
				reply := map[string]any{
					"jsonrpc": "2.0", "id": id, "ok": true,
					"scopes": []string{"read", "ui", "admin"}, "app_version": "test",
				}
				if caps != nil {
					reply["caps"] = caps
				}
				_ = conn.WriteJSON(reply)
				continue
			}
			result := map[string]any{"method": method}
			h.mu.Lock()
			switch method {
			case "get_device_info":
				if h.deviceInfo != nil {
					result = map[string]any{}
					for k, v := range h.deviceInfo {
						result[k] = v
					}
				}
			case "get_caps":
				if h.capsResult != nil {
					result = map[string]any{"caps": h.capsResult}
				}
			case "enable_accessibility":
				result = map[string]any{
					"enabled": true, "connected": true, "via": "shizuku",
				}
			}
			ev := h.preEvent
			rejectCaps := h.rejectCaps
			h.mu.Unlock()
			if method == "get_caps" && rejectCaps {
				_ = conn.WriteJSON(map[string]any{
					"jsonrpc": "2.0", "id": id, "ok": false,
					"code": "METHOD_NOT_ALLOWED", "error": "método desconocido: get_caps",
				})
				continue
			}
			// v2.3.1: evento asíncrono sin `id` antes de la respuesta real.
			if ev != nil {
				_ = conn.WriteJSON(ev)
			}
			_ = conn.WriteJSON(map[string]any{
				"jsonrpc": "2.0", "id": id, "ok": true,
				"result": result,
			})
		}
	}))
	return h
}

func (h *wsHarness) url() string {
	return "ws" + strings.TrimPrefix(h.srv.URL, "http")
}

func (h *wsHarness) counts() (hellos, conns, graceful int) {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.hellos, h.conns, h.gracefulClose
}

// waitGraceful espera (≤2 s) a que el servidor registre `want` cierres
// ordenados. Bajo carga (suite completa) el eco del frame `close` puede
// llegar después del deadline del cliente; el test no debe asumir
// scheduling inmediato.
func (h *wsHarness) waitGraceful(want int) int {
	deadline := time.Now().Add(2 * time.Second)
	for {
		_, _, g := h.counts()
		if g >= want || time.Now().After(deadline) {
			return g
		}
		time.Sleep(10 * time.Millisecond)
	}
}

// pointClientAt apunta el cliente a este harness en un archivo de config
// temporal y resetea la sesión compartida.
func (h *wsHarness) pointClientAt(t *testing.T) {
	t.Setenv("JAV_WS_URL", h.url())
	t.Setenv("JAV_TOKEN", "test-token")
	t.Setenv("JAV_CONFIG", filepath.Join(t.TempDir(), "config.json"))
	resetShared()
	t.Cleanup(resetShared)
}

// v1.2.1: la sesión persistente reutiliza UNA conexión — N tool calls
// generan 1 solo `hello` (antes: 1 hello por call).
func TestPersistentReusesOneHello(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	for i := 0; i < 4; i++ {
		if _, jerr := c.Call("get_battery", nil); jerr != nil {
			t.Fatalf("call %d: %v", i, jerr)
		}
	}
	hellos, conns, _ := h.counts()
	if hellos != 1 {
		t.Fatalf("hellos=%d, esperado 1 (sesión persistente)", hellos)
	}
	if conns != 1 {
		t.Fatalf("conns=%d, esperado 1", conns)
	}
}

// v1.2.1: si el servidor tira la conexión, la siguiente llamada reconecta
// (hello nuevo) y reintenta una vez antes de fallar.
func TestReconnectAfterServerDrop(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("call 1: %v", jerr)
	}
	h.forceClose <- struct{}{}
	time.Sleep(150 * time.Millisecond)
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("reconexión: %v", jerr)
	}
	hellos, conns, _ := h.counts()
	if hellos != 2 || conns != 2 {
		t.Fatalf("hellos=%d conns=%d, esperado 2/2 tras reconexión", hellos, conns)
	}
}

// regresión del "dummy token": un hello rechazado por el teléfono
// (`{ok:false, code:"UNAUTHORIZED"}`) NUNCA debe tratarse como sesión válida.
// Antes del fix, `dialConn` usaba `raw` (sin mirar `ok`) y devolvía un
// cliente como si la autenticación hubiera pasado.
func TestDialRejectsUnauthorized(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.rejectHello = true
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr == nil {
		t.Fatalf("Dial() aceptó un hello UNAUTHORIZED; cliente=%v (bug de bypass)", c)
	}
	if jerr.Code != "UNAUTHORIZED" {
		t.Fatalf("code=%q, esperado UNAUTHORIZED", jerr.Code)
	}
	hellos, _, _ := h.counts()
	if hellos != 1 {
		t.Fatalf("hellos=%d, esperado 1", hellos)
	}
}

// regresión de la cara visible del bug: `jav pair` no debe reportar
// "Vinculado" ni escribir el config cuando el token es rechazado.
func TestPairRejectsUnauthorizedDoesNotPersist(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.rejectHello = true
	cfg := filepath.Join(t.TempDir(), "config.json")
	t.Setenv("JAV_CONFIG", cfg)
	resetShared()
	t.Cleanup(resetShared)

	if _, err := Pair(h.url(), "token-falso"); err == nil {
		t.Fatal("Pair() aceptó un token falso (bug: reporta Vinculado sin autenticar)")
	}
	if _, err := os.Stat(cfg); err == nil {
		t.Fatalf("Pair() persistió %s pese a UNAUTHORIZED", cfg)
	}
}

// v1.2.5: el hello trae `caps` (grants/estado) y el cliente los expone
// para `device_status`; app sin caps (<1.2.5) → mapa nil (no se inventa).
func TestHelloCapturesCaps(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.helloCaps = map[string]any{
		"shizuku": true, "accessibility": false, "contacts": true, "ruido": "x",
	}
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	if c.Caps == nil {
		t.Fatal("Caps nil con hello que trae caps")
	}
	if !c.Caps["shizuku"] || !c.Caps["contacts"] {
		t.Fatalf("caps true perdidos: %v", c.Caps)
	}
	if c.Caps["accessibility"] {
		t.Fatalf("caps false mal parseado: %v", c.Caps)
	}
	if _, ok := c.Caps["ruido"]; ok {
		t.Fatalf("valor no-bool no debe entrar en caps: %v", c.Caps)
	}

	// hello sin caps (app <1.2.5) → nil, sin inventar defaults.
	h2 := newWsHarness(t)
	defer h2.srv.Close()
	h2.pointClientAt(t)
	c2, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial 2: %v", jerr)
	}
	if c2.Caps != nil {
		t.Fatalf("Caps=%v, esperado nil sin caps en hello", c2.Caps)
	}
}

// v1.2.1 (regresión del bug BUSY): el cierre de la sesión persistente
// envía un frame `close` ordenado para que el teléfono libere el slot
// single-client de inmediato (no tras ~2 min de timeout).
func TestResetSharedSendsCloseFrame(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.pointClientAt(t)

	if _, jerr := Dial(); jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	resetShared()
	if graceful := h.waitGraceful(1); graceful != 1 {
		t.Fatalf("gracefulCloses=%d, esperado 1 (frame close ordenado)", graceful)
	}
}

// v2.0.0: ListPackages envía el método WS `list_packages` con su filtro
// (sin `adb` en el host; funciona en Termux/WSS).
func TestListPackagesSendsWSMethod(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	res, jerr := c.ListPackages("foo")
	if jerr != nil {
		t.Fatalf("ListPackages: %v", jerr)
	}
	if got, _ := res["method"].(string); got != "list_packages" {
		t.Fatalf("method=%q, esperado list_packages", got)
	}
}

// v2.2.0: dos teléfonos vinculados, cambio de foco en caliente y cierre
// ordenado de la sesión anterior (sin fugas de estado entre dispositivos).
func TestMultiDevicePairAndSelect(t *testing.T) {
	h1 := newWsHarness(t)
	defer h1.srv.Close()
	h2 := newWsHarness(t)
	defer h2.srv.Close()

	t.Setenv("JAV_CONFIG", filepath.Join(t.TempDir(), "config.json"))
	t.Setenv("JAV_WS_URL", "")
	t.Setenv("JAV_TOKEN", "")
	t.Setenv("JAV_DEVICE", "")
	t.Setenv("JAV_CERT_FINGERPRINT", "")
	resetShared()
	t.Cleanup(resetShared)

	if _, err := PairNamed("phone-a", h1.url(), "tok-a"); err != nil {
		t.Fatalf("pair phone-a: %v", err)
	}
	if _, err := PairNamed("phone-b", h2.url(), "tok-b"); err != nil {
		t.Fatalf("pair phone-b: %v", err)
	}
	if got := ActiveDeviceName(); got != "phone-b" {
		t.Fatalf("active=%q, esperado phone-b", got)
	}
	if names := PairedDeviceNames(); len(names) != 2 ||
		names[0] != "phone-a" || names[1] != "phone-b" {
		t.Fatalf("paired=%v, esperado [phone-a phone-b]", names)
	}

	// Sesión activa: el tráfico va al phone-b.
	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial phone-b: %v", jerr)
	}
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("call phone-b: %v", jerr)
	}
	if hellos, _, _ := h2.counts(); hellos != 2 {
		t.Fatalf("h2 hellos=%d, esperado 2 (pair + sesión)", hellos)
	}
	if hellos, _, _ := h1.counts(); hellos != 1 {
		t.Fatalf("h1 hellos=%d, esperado 1 (solo pair)", hellos)
	}

	// Cambio de foco: la sesión de h2 se cierra con frame close ordenado.
	// El cierre del `pair` es asíncrono: se espera a que el servidor lo
	// registre antes de medir, para no confundirlo con el de la sesión
	// (el eco puede llegar en el mismo intervalo de sondeo: 0→2).
	if g := h2.waitGraceful(1); g != 1 {
		t.Fatalf("h2 no registró el cierre ordenado del pair: %d", g)
	}
	_, _, gracefulBefore := h2.counts()
	if _, err := SelectDevice("phone-a"); err != nil {
		t.Fatalf("select phone-a: %v", err)
	}
	if got := ActiveDeviceName(); got != "phone-a" {
		t.Fatalf("active=%q tras select, esperado phone-a", got)
	}
	if _, jerr := c.Call("get_battery", nil); jerr != nil {
		t.Fatalf("call phone-a: %v", jerr)
	}
	if hellos, _, _ := h1.counts(); hellos != 2 {
		t.Fatalf("h1 hellos=%d, esperado 2 (pair + nueva sesión)", hellos)
	}
	if after := h2.waitGraceful(gracefulBefore + 1); after < gracefulBefore+1 {
		t.Fatalf("h2 no cerró la sesión ordenadamente: before=%d after=%d",
			gracefulBefore, after)
	}
}

// v2.4.0 (Fase 4): `get_caps` refresca los caps EN VIVO (aunque el hello
// trajera accessibility=false) y `enable_accessibility` devuelve el estado
// de la reparación. Son las dos piezas que desacoplan `device_status` del
// servicio de accesibilidad.
func TestGetCapsAndEnableAccessibility(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.helloCaps = map[string]any{"accessibility": false, "shizuku": true}
	h.mu.Lock()
	h.capsResult = map[string]any{"accessibility": true, "shizuku": true}
	h.mu.Unlock()
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	if c.Caps["accessibility"] {
		t.Fatalf("caps del hello: accessibility debe ser false, got %v", c.Caps)
	}

	caps, jerr := c.GetCaps()
	if jerr != nil {
		t.Fatalf("GetCaps: %v", jerr)
	}
	if !caps["accessibility"] || !caps["shizuku"] {
		t.Fatalf("caps vivos mal parseados: %v", caps)
	}
	if !c.Caps["accessibility"] {
		t.Fatalf("GetCaps no actualizó c.Caps: %v", c.Caps)
	}

	rep, jerr := c.EnableAccessibility()
	if jerr != nil {
		t.Fatalf("EnableAccessibility: %v", jerr)
	}
	if enabled, _ := rep["enabled"].(bool); !enabled {
		t.Fatalf("enable_accessibility no devolvió enabled: %v", rep)
	}
	if via, _ := rep["via"].(string); via != "shizuku" {
		t.Fatalf("via=%q, esperado shizuku", via)
	}
}

// v2.4.0: una APK <2.4.0 responde METHOD_NOT_ALLOWED a `get_caps`; el
// cliente debe propagar el código para que `device_status` caiga a los
// caps del hello sin inventar estado.
func TestGetCapsMethodNotAllowed(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.rejectCaps = true
	h.pointClientAt(t)

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	if _, jerr := c.GetCaps(); jerr == nil || jerr.Code != "METHOD_NOT_ALLOWED" {
		t.Fatalf("GetCaps app vieja: jerr=%v, esperado METHOD_NOT_ALLOWED", jerr)
	}
}

// v2.3.1: el teléfono intercala EVENTOS sin `id` (p. ej. `shell_grant` al
// conceder el permiso) antes de la respuesta. El cliente debe descartarlos
// y quedarse con la respuesta real; antes la llamada moría con JAM_ERROR
// aunque el comando sí se hubiera ejecutado.
func TestCallSkipsEventFrames(t *testing.T) {
	h := newWsHarness(t)
	defer h.srv.Close()
	h.pointClientAt(t)
	h.mu.Lock()
	h.preEvent = map[string]any{"event": "shell_grant", "mode": "5m", "sha256": "deadbeef"}
	h.mu.Unlock()

	c, jerr := Dial()
	if jerr != nil {
		t.Fatalf("dial: %v", jerr)
	}
	res, jerr := c.Call("shell", map[string]any{"cmd": "id", "timeout_ms": 1000})
	if jerr != nil {
		t.Fatalf("call con evento intercalado: %v", jerr)
	}
	if got, _ := res["method"].(string); got != "shell" {
		t.Fatalf("resultado inesperado: %#v", res)
	}
}
