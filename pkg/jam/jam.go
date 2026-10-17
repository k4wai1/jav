package jam

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Protocolo Jav: PROTOCOL.md. Sin Jev: hello + dump_ui + tap.
// Equivale a socket_client.py + tools/_base.py.

const ProtocolVersion = 1

// MaxFrameBytes es el frame WS máximo (AGENTS.md §3.6: 4 MiB).
const MaxFrameBytes = 4 * 1024 * 1024

// closeTimeout acota el handshake de cierre (`close` + eco del peer) para
// que el servidor libere su slot single-client antes de la siguiente
// conexión (ver Client.Close).
const closeTimeout = 500 * time.Millisecond

// ClientVersion se inyecta por -ldflags -X main.version=… (spec §1).
var ClientVersion = "0.1.0"

// JamError es un fallo honesto del dispatcher Jav (código + mensaje).
type JamError struct {
	Code    string
	Message string
}

func (e *JamError) Error() string { return e.Code + ": " + e.Message }

// hintFor mapea código Jav → hint accionable (recovery_instruction,
// guía §3.2). Las filas originales son el núcleo canónico y no se tocan
// (compatibilidad forense); aquí solo se extienden las restantes.
func hintFor(code string) string {
	switch code {
	case "STALE_SNAPSHOT":
		return "re-haz read_screen y usa el snapshot nuevo"
	case "NOT_FOCUSED":
		return "haz tap sobre el campo antes de type_text"
	case "SELECTOR_NOT_FOUND":
		return "re-haz read_screen; el selector no matchea"
	case "ACCESSIBILITY_DISABLED":
		return "habilita Jav en Ajustes → Accesibilidad"
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
		return "sin token: ejecuta en terminal `jav pair <IP_TAILNET> <TOKEN>` (no hace falta reiniciar el MCP)"
	// --- Extensión guía §3.2 (v1): sin cambiar las anteriores ---
	case "SHIZUKU_DENIED":
		return "concede el permiso runtime de Shizuku a Jav y reintenta"
	case "FORBIDDEN":
		return "pide scope/permiso correspondiente; no reintentes el mismo payload"
	case "VALIDATION_ERROR":
		return "revisa los parametros de la tool (forma, enum, rangos, unidades)"
	case "INTENT_UNRESOLVED":
		return "elige otra app destino o abre sin package (chooser) y verifica"
	case "PACKAGE_NOT_FOUND":
		return "verifica el paquete con list_packages; el paquete lo aporta el operador, no lo adivines"
	case "CLIPBOARD_EMPTY":
		return "copia primero en la app-origen y re-lee (host dumpsys o pegado-readback); no inventes contenido"
	case "UI_UNSTABLE":
		return "para: dif de forenses + informe (firma igual en 2 corridas = no relanzar)"
	case "VERIFY_FAILED":
		return "confirma con get_foreground/read_screen; si no llegó, un reintento y luego informe"
	case "CONNECTION_FAILED":
		return "revisa la conexion (adb forward o WSS tailnet); si aun no vinculaste: `jav pair <IP_TAILNET> <TOKEN>` en terminal (sin reiniciar el MCP)"
	case "CERT_MISMATCH":
		return "el cert del tailnet cambió: re-verifica el fingerprint en la app (cert_sha256) y actualiza el pin; no continues a ciegas"
	case "RATE_LIMITED", "BUSY":
		return "espera y reintenta con backoff; segundo cliente recibe BUSY"
	case "SHELL_DENIED", "SHELL_DENYLIST":
		return "pide grant en el dispositivo (1 comando/5 min/30 min); denylist exige admin + confirm:true"
	case "USAGE_ACCESS_DISABLED", "CONTACTS_PERMISSION_DENIED",
		"CALENDAR_PERMISSION_DENIED", "NOTIFICATION_LISTENER_DISABLED",
		"MEDIA_SESSIONS_UNAVAILABLE", "LOCATION_PERMISSION_DENIED",
		"CAMERA_DENIED", "WRITE_SETTINGS_DISABLED":
		return "concede el acceso en el dispositivo (estado visible en hello.caps) y reintenta; sin grant, error honesto"
	case "NOTIFICATION_GONE", "NO_REMOTE_INPUT", "REPLY_FAILED",
		"MEDIA_SESSION_GONE", "MEDIA_CONTROL_FAILED",
		"LOCATION_UNAVAILABLE", "LOCATION_TIMEOUT",
		"CAMERA_UNAVAILABLE", "CAMERA_FAILED",
		"SETTINGS_PUT_FAILED", "CALENDAR_UNAVAILABLE", "INTENT_FAILED":
		return "re-observe el destino (lista/sesiones/permiso) y decide de nuevo; nunca inventes el efecto"
	}
	return "revisa evidence.code/error y re-observe el estado antes de reintentar (nunca reintentes el mismo payload a ciegas)"
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

// WSURL resuelve la URL del servidor Jav con prioridad
// env (`JAV_WS_URL`/`JEV_WS_URL`) → `~/.config/jav/config.json` → default
// loopback. Se relee en caliente (v1.2.1: `jav pair` sin reiniciar el MCP).
func WSURL() string {
	return firstNonEmpty(
		os.Getenv("JAV_WS_URL"),
		os.Getenv("JEV_WS_URL"),
		LoadConfig().WSURL,
		"ws://127.0.0.1:38472/",
	)
}

// TokenOrEmpty resuelve el token (env → config) sin error.
func TokenOrEmpty() string {
	return firstNonEmpty(
		os.Getenv("JAV_TOKEN"),
		os.Getenv("JEV_TOKEN"),
		LoadConfig().Token,
	)
}

// Token resuelve el token; sin él → error honesto UNAUTHORIZED (nunca
// cuelga, nunca inventa) con hint de `jav pair`.
func Token() (string, *JamError) {
	if t := TokenOrEmpty(); t != "" {
		return t, nil
	}
	return "", &JamError{Code: "UNAUTHORIZED",
		Message: "sin token: ejecuta `jav pair <IP_TAILNET> <TOKEN>` en terminal (o define JAV_TOKEN)"}
}

// certFingerprint resuelve el pin SHA-256 del cert del tailnet con
// prioridad env (`JAV_CERT_FINGERPRINT`/`JEV_CERT_FINGERPRINT`) →
// `config.json`. Vacío = TOFU sin pin (se captura y guarda al conectar).
func certFingerprint() string {
	for _, k := range []string{"JAV_CERT_FINGERPRINT", "JEV_CERT_FINGERPRINT"} {
		if v := os.Getenv(k); v != "" {
			return normalizeFP(v)
		}
	}
	return normalizeFP(LoadConfig().CertFingerprint)
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

// Client es el ÚNICO que habla WS con Jav (spec §2 regla 2).
type Client struct {
	URL        string
	Token      string
	Scopes     []string
	AppVersion string
	conn       *websocket.Conn
}

// --- Sesión persistente (política single-client del teléfono) -----------
//
// El servidor del teléfono es single-client y procesa frames en serie. En
// vez de abrir/cerrar un WSS por tool call (≈1.3 s de TLS+WS por llamada,
// v1.2.0), se mantiene UNA conexión compartida y se serializa con
// `sharedMu`: N llamadas = 1 solo `hello`. Un cambio de configuración en
// caliente (env o `~/.config/jav/config.json`) fuerza reconexión.
var (
	sharedMu     sync.Mutex
	sharedClient *Client
	sharedCfg    string
)

// effectiveConfig identifica la sesión como `url|token|fp`.
func effectiveConfig() string {
	return WSURL() + "|" + TokenOrEmpty() + "|" + certFingerprint()
}

// Dial devuelve la sesión compartida (la abre si no existe o si la
// configuración cambió). Igual que _base.jam_client: ante connection
// refused en loopback crea el forward y reintenta UNA vez.
func Dial() (*Client, *JamError) {
	sharedMu.Lock()
	defer sharedMu.Unlock()
	return acquireSharedLocked()
}

// acquireSharedLocked exige `sharedMu` tomado.
func acquireSharedLocked() (*Client, *JamError) {
	cfg := effectiveConfig()
	if sharedClient != nil && sharedCfg != cfg {
		sharedClient.closeConn()
		sharedClient = nil
	}
	if sharedClient != nil {
		return sharedClient, nil
	}
	url := WSURL()
	token, terr := Token()
	if terr != nil {
		return nil, terr
	}
	fp := certFingerprint()
	c, captured, jerr := dialConn(url, token, fp)
	if jerr != nil && isLoopback(url) && isRefused(jerr) {
		EnsureForward()
		c, captured, jerr = dialConn(url, token, fp)
	}
	if jerr != nil {
		return nil, jerr
	}
	// Auto-TOFU: si conectamos a wss:// sin pin, fijamos el observado.
	if captured != "" {
		if err := UpdateConfig(func(cf *Config) { cf.CertFingerprint = captured }); err == nil {
			fmt.Fprintf(os.Stderr, "jav: Auto-TOFU %s… guardado en %s\n",
				captured[:min(16, len(captured))], ConfigPath())
		}
	}
	sharedClient = c
	sharedCfg = effectiveConfig() // post-TOFU
	return sharedClient, nil
}

func isRefused(e *JamError) bool {
	m := strings.ToLower(e.Message)
	return strings.Contains(m, "refused") || strings.Contains(m, "connection reset") ||
		strings.Contains(m, "no such host") || strings.Contains(m, "timeout") ||
		strings.Contains(m, "no route to host")
}

// pinnedTLSConfig arma el tls.Config de un bind `wss://`: TOFU con
// verificación por pin SHA-256 cuando `fp` no está vacío (comparación en
// tiempo constante). Sin pin acepta y (si `captured` != nil) deja el
// fingerprint observado para el Auto-TOFU de v1.2.1.
func pinnedTLSConfig(fp string) *tls.Config {
	return pinnedTLSConfigCapture(fp, nil)
}

func pinnedTLSConfigCapture(fp string, captured *string) *tls.Config {
	return &tls.Config{
		// TOFU: certificado autofirmado; si hay fingerprint, se pinnea abajo.
		InsecureSkipVerify: true,
		VerifyConnection: func(cs tls.ConnectionState) error {
			if len(cs.PeerCertificates) == 0 {
				return fmt.Errorf("servidor sin certificado")
			}
			sum := sha256.Sum256(cs.PeerCertificates[0].Raw)
			got := hex.EncodeToString(sum[:])
			if fp == "" {
				if captured != nil {
					*captured = got
				}
				return nil
			}
			if subtle.ConstantTimeCompare([]byte(got), []byte(fp)) != 1 {
				return fmt.Errorf("fingerprint TLS no coincide (TOFU)")
			}
			return nil
		},
	}
}

// dialConn abre + `hello` sobre url/token/fp explícitos. Devuelve el
// fingerprint observado (Auto-TOFU cuando `fp`="" en `wss://`).
func dialConn(url, token, fp string) (*Client, string, *JamError) {
	d := websocket.Dialer{HandshakeTimeout: 10 * time.Second}
	var captured string
	if strings.HasPrefix(strings.ToLower(url), "wss://") {
		d.TLSClientConfig = pinnedTLSConfigCapture(fp, &captured)
	}
	conn, _, err := d.Dial(url, nil)
	if err != nil {
		code := "CONNECTION_FAILED"
		if fp != "" && strings.Contains(err.Error(), "fingerprint TLS") {
			code = "CERT_MISMATCH"
		}
		return nil, "", &JamError{Code: code, Message: err.Error()}
	}
	conn.SetReadLimit(MaxFrameBytes)
	c := &Client{URL: url, Token: token, conn: conn}
	hello, jerr := c.raw("hello", map[string]any{
		"protocol_version": ProtocolVersion,
		"client_version":   ClientVersion,
		"token":            token,
		"client":           "jav-go/" + ClientVersion,
	})
	if jerr != nil {
		_ = conn.WriteControl(websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseInternalServerErr, ""),
			time.Now().Add(closeTimeout))
		_ = conn.Close()
		return nil, "", jerr
	}
	// El hello es la puerta de autenticación: `raw` NO valida el campo `ok`
	// (la respuesta plana trae scopes/app_version en la raíz, no en `result`).
	// Sin este guard un `{ok:false, code:"UNAUTHORIZED"}` se trataba como
	// éxito → `jav pair` reportaba "Vinculado" con un token falso y fijaba el
	// pin TOFU sobre una sesión no autenticada.
	if ok, _ := hello["ok"].(bool); !ok {
		code, _ := hello["code"].(string)
		msg, _ := hello["error"].(string)
		if code == "" {
			code = "UNAUTHORIZED"
		}
		_ = conn.WriteControl(websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseInternalServerErr, ""),
			time.Now().Add(closeTimeout))
		_ = conn.Close()
		return nil, "", &JamError{Code: code, Message: msg}
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
	return c, captured, nil
}

// Close cierra el WS con handshake ordenado (frame `close` + eco del peer,
// 1 RTT acotado por closeTimeout). Necesario porque el servidor Android
// aplica política single-client: un cierre abrupto (solo TCP FIN, sin
// frame `close`) no dispara `onClose` hasta su timeout de conexión perdida
// (~2 min), dejando el slot en BUSY.
//
// En v1.2.1 la sesión de trabajo es persistente y compartida: `Close()`
// sobre el cliente compartido es un no-op (no rompe el pool). El cierre
// real ocurre al cambiar la config en caliente o con `resetShared`.
func (c *Client) Close() {
	if c == nil {
		return
	}
	sharedMu.Lock()
	isShared := c == sharedClient
	sharedMu.Unlock()
	if isShared {
		return
	}
	c.closeConn()
}

// closeConn cierra la conexión con handshake ordenado. No toma sharedMu.
func (c *Client) closeConn() {
	if c == nil || c.conn == nil {
		return
	}
	conn := c.conn
	c.conn = nil
	_ = conn.WriteControl(websocket.CloseMessage,
		websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
		time.Now().Add(closeTimeout))
	_ = conn.SetReadDeadline(time.Now().Add(closeTimeout))
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			break
		}
	}
	_ = conn.Close()
}

// resetShared cierra y olvida la sesión compartida (tests / shutdown).
func resetShared() {
	sharedMu.Lock()
	defer sharedMu.Unlock()
	if sharedClient != nil {
		sharedClient.closeConn()
		sharedClient = nil
	}
	sharedCfg = ""
}

func newID() string {
	var b [4]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (c *Client) raw(method string, params map[string]any) (map[string]any, *JamError) {
	if c.conn == nil {
		return nil, &JamError{Code: "CONNECTION_FAILED", Message: "conexión no inicializada"}
	}
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

// CallTimeout ejecuta un método sobre la **sesión persistente compartida**
// (adquiere sharedMu). Ante un error de transporte (EOF/pipe roto/reset)
// cierra la conexión, reconecta UNA vez y reintenta antes de fallar.
func (c *Client) CallTimeout(method string, params map[string]any, readTimeout time.Duration) (map[string]any, *JamError) {
	sharedMu.Lock()
	defer sharedMu.Unlock()
	cli, jerr := acquireSharedLocked()
	if jerr != nil {
		return nil, jerr
	}
	res, jerr := cli.callOnConn(method, params, readTimeout)
	if jerr != nil && isTransportError(jerr) {
		cli.closeConn()
		if sharedClient == cli {
			sharedClient = nil
		}
		cli2, jerr2 := acquireSharedLocked()
		if jerr2 != nil {
			return nil, jerr2
		}
		res, jerr = cli2.callOnConn(method, params, readTimeout)
	}
	return res, jerr
}

// callOnConn ejecuta un método sobre ESTA conexión (sin tocar sharedMu).
func (c *Client) callOnConn(method string, params map[string]any, readTimeout time.Duration) (map[string]any, *JamError) {
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

// isTransportError distingue un fallo de socket (reintentable con
// reconexión) de un error lógico del servidor. `CONNECTION_FAILED` solo se
// genera en el cliente (dial/lectura/escritura); el único caso lógico es
// BUSY (cierre 4001 por la política single-client), que NO se reintenta.
func isTransportError(e *JamError) bool {
	if e == nil || e.Code != "CONNECTION_FAILED" {
		return false
	}
	return !strings.Contains(strings.ToLower(e.Message), "busy")
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

// GetAudit consulta el ring buffer de auditoría del dispositivo (Fase 6a):
// limit 1..200 (default 50), since_seq filtra seq > since_seq.
func (c *Client) GetAudit(limit int, sinceSeq int64) (map[string]any, *JamError) {
	return c.Call("get_audit", map[string]any{"limit": limit, "since_seq": sinceSeq})
}

// Shell ejecuta un comando con UID shell vía Shizuku (Fase 6b, scope admin).
// La request puede bloquear hasta 60 s esperando el grant interactivo; el
// readTimeout cubre grant + ejecución.
func (c *Client) Shell(cmd string, timeoutMs int, confirm bool) (map[string]any, *JamError) {
	if timeoutMs <= 0 {
		timeoutMs = 15000
	}
	read := time.Duration(timeoutMs)*time.Millisecond + 65*time.Second
	return c.CallTimeout("shell", map[string]any{
		"cmd":        cmd,
		"timeout_ms": timeoutMs,
		"confirm":    confirm,
	}, read)
}

var _ = fmt.Sprint
