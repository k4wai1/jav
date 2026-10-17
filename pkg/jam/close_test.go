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
			_ = conn.WriteJSON(map[string]any{
				"jsonrpc": "2.0", "id": id, "ok": true,
				"result": map[string]any{"method": method},
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
	_, _, graceful := h.counts()
	if graceful != 1 {
		t.Fatalf("gracefulCloses=%d, esperado 1 (frame close ordenado)", graceful)
	}
}
