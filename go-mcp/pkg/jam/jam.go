package jam

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

// Protocolo Jam: PROTOCOL.md. Sin Jev: hello + dump_ui + tap.
// Equivale a socket_client.py + tools/_base.py.

const ProtocolVersion = 1

// MaxFrameBytes es el frame WS máximo (AGENTS.md §3.6: 4 MiB).
const MaxFrameBytes = 4 * 1024 * 1024

// ClientVersion se inyecta por -ldflags -X main.version=… (spec §1).
var ClientVersion = "0.1.0"

// JamError es un fallo honesto del dispatcher Jam (código + mensaje).
type JamError struct {
	Code    string
	Message string
}

func (e *JamError) Error() string { return e.Code + ": " + e.Message }

// hintFor mapea código Jam → hint accionable (idéntico a _base.jam_fail).
func hintFor(code string) string {
	switch code {
	case "STALE_SNAPSHOT":
		return "re-haz read_screen y usa el snapshot nuevo"
	case "NOT_FOCUSED":
		return "haz tap sobre el campo antes de type_text"
	case "SELECTOR_NOT_FOUND":
		return "re-haz read_screen; el selector no matchea"
	case "ACCESSIBILITY_DISABLED":
		return "habilita Jam en Ajustes → Accesibilidad"
	case "SHIZUKU_UNAVAILABLE":
		return "arranca Shizuku y reintenta"
	case "TIMEOUT":
		return "reintenta o sube el timeout"
	case "SECURE_SURFACE":
		return "la ventana tiene FLAG_SECURE; usa dump_ui, no screenshot"
	case "PAYLOAD_TOO_LARGE":
		return "reintenta con fmt webp y quality 80"
	case "METHOD_NOT_ALLOWED":
		return "metodo no disponible en esta fase; no reintentes igual"
	case "UNAUTHORIZED":
		return "revisa JAV_TOKEN en el entorno del servidor"
	}
	return ""
}

// Envelope es la envolvente {ok, verified, evidence, hint} (AGENTS.md §6).
type Envelope map[string]any

// OK construye envolvente de éxito.
func OK(verified bool, evidence map[string]any, hint string) Envelope {
	return Envelope{"ok": true, "verified": verified, "evidence": evidence, "hint": hint}
}

// Fail construye envolvente de fallo honesto.
func Fail(code, message, hint string) Envelope {
	return Envelope{"ok": false, "verified": false,
		"evidence": map[string]any{"code": code, "error": message}, "hint": hint}
}

// JamFail traduce JamError a envolvente con hint (equiv. _base.jam_fail).
func JamFail(e *JamError) Envelope {
	return Fail(e.Code, e.Message, hintFor(e.Code))
}

// WSURL lee JAV_WS_URL con fallback JEV_WS_URL (spec §8).
func WSURL() string {
	if u := os.Getenv("JAV_WS_URL"); u != "" {
		return u
	}
	if u := os.Getenv("JEV_WS_URL"); u != "" {
		return u
	}
	return "ws://127.0.0.1:38472/"
}

// Token lee JAV_TOKEN con fallback JEV_TOKEN. Sin token → error honesto
// UNAUTHORIZED (nunca cuelga, nunca inventa).
func Token() (string, *JamError) {
	if t := os.Getenv("JAV_TOKEN"); t != "" {
		return t, nil
	}
	if t := os.Getenv("JEV_TOKEN"); t != "" {
		return t, nil
	}
	return "", &JamError{Code: "UNAUTHORIZED", Message: "sin token (JAV_TOKEN ausente en el entorno)"}
}

// isLoopback dice si la URL apunta a loopback (solo ahí vale auto-forward).
func isLoopback(url string) bool {
	u := strings.ToLower(url)
	return strings.Contains(u, "127.0.0.1") || strings.Contains(u, "localhost")
}

// EnsureForward crea el forward adb (solo loopback). Equiv. _base.ensure_forward.
func EnsureForward() {
	_ = exec.Command("adb", "forward", "tcp:38472", "tcp:38472").Run()
}

// Client es el ÚNICO que habla WS con Jam (spec §2 regla 2).
type Client struct {
	URL        string
	Token      string
	Scopes     []string
	AppVersion string
	conn       *websocket.Conn
}

// Dial conecta + hello; ante connection refused en loopback crea el
// forward y reintenta UNA vez (igual que _base.jam_client).
func Dial() (*Client, *JamError) {
	url := WSURL()
	token, terr := Token()
	if terr != nil {
		return nil, terr
	}
	c, jerr := dialOnce(url, token, 10*time.Second, 0)
	if jerr != nil && isLoopback(url) && isRefused(jerr) {
		EnsureForward()
		c, jerr = dialOnce(url, token, 10*time.Second, 0)
	}
	return c, jerr
}

func isRefused(e *JamError) bool {
	m := strings.ToLower(e.Message)
	return strings.Contains(m, "refused") || strings.Contains(m, "connection reset") ||
		strings.Contains(m, "no such host") || strings.Contains(m, "timeout") ||
		strings.Contains(m, "no route to host")
}

func dialOnce(url, token string, timeout, readTimeout time.Duration) (*Client, *JamError) {
	d := websocket.Dialer{HandshakeTimeout: timeout}
	conn, _, err := d.Dial(url, nil)
	if err != nil {
		return nil, &JamError{Code: "CONNECTION_FAILED", Message: err.Error()}
	}
	conn.SetReadLimit(MaxFrameBytes)
	c := &Client{URL: url, Token: token, conn: conn}
	if readTimeout > 0 {
		_ = conn.SetReadDeadline(time.Now().Add(readTimeout))
	}
	hello, jerr := c.raw("hello", map[string]any{
		"protocol_version": ProtocolVersion,
		"client_version":   ClientVersion,
		"token":            token,
		"client":           "jav-go/" + ClientVersion,
	})
	if jerr != nil {
		_ = conn.Close()
		return nil, jerr
	}
	if sc, ok := hello["scopes"].([]any); ok {
		for _, s := range sc {
			if str, ok := s.(string); ok {
				c.Scopes = append(c.Scopes, str)
			}
		}
	}
	if v, ok := hello["app_version"].(string); ok {
		c.AppVersion = v
	}
	_ = conn.SetReadDeadline(time.Time{})
	return c, nil
}

// Close cierra el WS.
func (c *Client) Close() {
	if c != nil && c.conn != nil {
		_ = c.conn.Close()
		c.conn = nil
	}
}

func newID() string {
	var b [4]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (c *Client) raw(method string, params map[string]any) (map[string]any, *JamError) {
	if params == nil {
		params = map[string]any{}
	}
	req := map[string]any{"id": newID(), "method": method, "params": params}
	if err := c.conn.WriteJSON(req); err != nil {
		return nil, &JamError{Code: "CONNECTION_FAILED", Message: err.Error()}
	}
	var res map[string]any
	if err := c.conn.ReadJSON(&res); err != nil {
		msg := err.Error()
		if strings.Contains(msg, "read limit") || strings.Contains(msg, "message too large") {
			return nil, &JamError{Code: "PAYLOAD_TOO_LARGE",
				Message: "frame WS > 4 MiB"}
		}
		return nil, &JamError{Code: "CONNECTION_FAILED", Message: msg}
	}
	return res, nil
}

// Call lanza JamError si !ok; si ok devuelve `result` (equiv. call()).
func (c *Client) Call(method string, params map[string]any) (map[string]any, *JamError) {
	return c.CallTimeout(method, params, 0)
}

// CallTimeout permite deadline de lectura (p.ej. wait_for_node largo).
func (c *Client) CallTimeout(method string, params map[string]any, readTimeout time.Duration) (map[string]any, *JamError) {
	if readTimeout > 0 {
		_ = c.conn.SetReadDeadline(time.Now().Add(readTimeout))
		defer c.conn.SetReadDeadline(time.Time{})
	}
	res, jerr := c.raw(method, params)
	if jerr != nil {
		return nil, jerr
	}
	if ok, _ := res["ok"].(bool); !ok {
		code, _ := res["code"].(string)
		msg, _ := res["error"].(string)
		if code == "" {
			code = "JAM_ERROR"
		}
		if msg == "" {
			raw, _ := json.Marshal(res)
			msg = string(raw)
		}
		return nil, &JamError{Code: code, Message: msg}
	}
	out := map[string]any{}
	if r, ok := res["result"].(map[string]any); ok {
		out = r
	}
	return out, nil
}

// --- Métodos 1:1 (equiv. socket_client.py) ---

func (c *Client) DumpUI() (map[string]any, *JamError) {
	return c.Call("dump_ui", nil)
}

func (c *Client) Tap(selector map[string]any) (map[string]any, *JamError) {
	return c.Call("tap", map[string]any{"selector": selector})
}

func (c *Client) TapNode(nodeID string, snapshotID int64) (map[string]any, *JamError) {
	return c.Call("tap_node", map[string]any{"node_id": nodeID, "snapshot_id": snapshotID})
}

func (c *Client) TypeText(nodeID string, snapshotID int64, text string) (map[string]any, *JamError) {
	return c.Call("type", map[string]any{"node_id": nodeID, "snapshot_id": snapshotID, "text": text})
}

func (c *Client) GetForeground() (map[string]any, *JamError) {
	return c.Call("get_foreground", nil)
}

func (c *Client) WaitForNode(selector map[string]any, timeoutMs int) (map[string]any, *JamError) {
	dl := time.Duration(timeoutMs)*time.Millisecond + 15*time.Second
	return c.CallTimeout("wait_for_node",
		map[string]any{"selector": selector, "timeout_ms": timeoutMs}, dl)
}

func (c *Client) PressBack() (map[string]any, *JamError) {
	return c.Call("press_back", nil)
}

func (c *Client) PressHome() (map[string]any, *JamError) {
	return c.Call("press_home", nil)
}

func (c *Client) OpenApp(pkg string) (map[string]any, *JamError) {
	return c.Call("open_app", map[string]any{"package": pkg})
}

func (c *Client) ForceStop(pkg string) (map[string]any, *JamError) {
	return c.Call("force_stop", map[string]any{"package": pkg})
}

func (c *Client) Screenshot(fmtStr string, quality int) (map[string]any, *JamError) {
	return c.CallTimeout("screenshot",
		map[string]any{"format": fmtStr, "quality": quality}, 60*time.Second)
}

func (c *Client) SetClipboard(text string) (map[string]any, *JamError) {
	return c.Call("set_clipboard", map[string]any{"text": text})
}

// Scroll envía scroll con dirección y nodo opcional.
func (c *Client) Scroll(direction string, nodeID string) (map[string]any, *JamError) {
	p := map[string]any{"direction": direction}
	if nodeID != "" {
		p["node_id"] = nodeID
	}
	return c.Call("scroll", p)
}

var _ = fmt.Sprint
