// Harness jav-tokens: mide el presupuesto de tokens de ARRANQUE del servidor
// MCP `jav` con un tokenizer REAL (tiktoken), no con la aproximación bytes/4
// que usa cmd/audit-mcp.
//
// Habla JSON-RPC puro por stdio con el binario `jav` (sin dispositivo, sin
// token, sin red): initialize + tools/list + una ficha de Resource. Reporta:
//
//	instructions        tokens del bloque `instructions` de initialize
//	tools/list          tokens del payload completo (schemas + descripciones)
//	carga cognitiva     instructions + Σ descripciones (lo que se inyecta)
//	ficha individual    tokens de android://tool/<name>
//	total arranque      instructions + tools/list
//
// Uso:
//
//	go run ./cmd/jav-tokens --bin dist/jav-linux-amd64
//	go run ./cmd/jav-tokens --tool read_screen --encoding cl100k_base
//
// El conteo es reproducible por encoding; `cl100k_base` es la referencia por
// defecto (familia GPT-4). La comparación contra audit-mcp (bytes/4) se imprime
// para detectar desvíos >20% (ver docs/benchmarks/PERFORMANCE.md §9).
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"

	"github.com/pkoukk/tiktoken-go"
)

// client es un cliente JSON-RPC mínimo por stdio (newline-delimited JSON, el
// framing que usa mcp-go ServeStdio). No usa mcp-go para conservar los bytes
// EXACTOS del wire y poder tokenizarlos tal cual.
type client struct {
	cmd   *exec.Cmd
	stdin io.WriteCloser
	r     *bufio.Reader
	next  int
}

func start(bin string) (*client, error) {
	cmd := exec.Command(bin)
	cmd.Stderr = os.Stderr // logs del servidor a stderr (no contaminan stdout)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return &client{cmd: cmd, stdin: stdin, r: bufio.NewReaderSize(stdout, 1<<22), next: 1}, nil
}

func (c *client) write(v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	_, err = c.stdin.Write(append(b, '\n'))
	return err
}

func (c *client) notify(method string, params any) error {
	return c.write(map[string]any{"jsonrpc": "2.0", "method": method, "params": params})
}

// call envía una petición y devuelve el `result` crudo (sin re-serializar) de
// la respuesta con el id correspondiente.
func (c *client) call(method string, params any) (json.RawMessage, error) {
	id := c.next
	c.next++
	if err := c.write(map[string]any{"jsonrpc": "2.0", "id": id, "method": method, "params": params}); err != nil {
		return nil, err
	}
	for {
		line, err := c.r.ReadBytes('\n')
		if len(line) > 0 {
			var msg struct {
				ID     *int            `json:"id"`
				Result json.RawMessage `json:"result"`
				Error  *struct {
					Code    int    `json:"code"`
					Message string `json:"message"`
				} `json:"error"`
			}
			if jerr := json.Unmarshal(line, &msg); jerr == nil && msg.ID != nil && *msg.ID == id {
				if msg.Error != nil {
					return nil, fmt.Errorf("%s: RPC error %d: %s", method, msg.Error.Code, msg.Error.Message)
				}
				return msg.Result, nil
			}
			// Notificación / log / respuesta ajena: se ignora.
		}
		if err != nil {
			return nil, fmt.Errorf("%s: EOF esperando respuesta: %w", method, err)
		}
	}
}

func (c *client) close() {
	_ = c.stdin.Close()
	_ = c.cmd.Wait()
}

// stats es la foto de tokens medida.
type stats struct {
	instructions      int
	toolsList         int
	cognitive         int // instructions + Σ descripciones
	ficha             int
	total             int // instructions + tools/list
	toolCount         int
	instructionsLen   int
	instructionsWords int
	toolsListLen      int
	cognitiveLen      int
	fichaLen          int
}

func main() {
	bin := flag.String("bin", "dist/jav-linux-amd64", "ruta al binario jav")
	tool := flag.String("tool", "read_screen", "tool cuya ficha individual se mide")
	encoding := flag.String("encoding", "cl100k_base", "encoding tiktoken (cl100k_base, o200k_base, …)")
	flag.Parse()

	if _, err := os.Stat(*bin); err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: no encuentro el binario %q (%v)\n", *bin, err)
		fmt.Fprintln(os.Stderr, "  hint: make build   (o pasa --bin /ruta/a/jav)")
		os.Exit(2)
	}

	tke, err := tiktoken.GetEncoding(*encoding)
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: no pude cargar el encoding %q: %v\n", *encoding, err)
		fmt.Fprintln(os.Stderr, "  hint: el primer uso descarga el BPE (cl100k_base). Revisa red/caché (TIKTOKEN_CACHE_DIR).")
		os.Exit(2)
	}
	count := func(s string) int { return len(tke.Encode(s, nil, nil)) }

	c, err := start(*bin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: no pude arrancar %q: %v\n", *bin, err)
		os.Exit(1)
	}
	defer c.close()

	initRes, err := c.call("initialize", map[string]any{
		"protocolVersion": "2024-11-05",
		"capabilities":    map[string]any{},
		"clientInfo":      map[string]any{"name": "jav-tokens", "version": "1.0"},
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: initialize falló: %v\n", err)
		os.Exit(1)
	}
	if err := c.notify("notifications/initialized", map[string]any{}); err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: no pude notificar initialized: %v\n", err)
		os.Exit(1)
	}

	var initObj struct {
		Instructions string `json:"instructions"`
	}
	_ = json.Unmarshal(initRes, &initObj)

	toolsRes, err := c.call("tools/list", map[string]any{})
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: tools/list falló: %v\n", err)
		os.Exit(1)
	}

	var toolsObj struct {
		Tools []struct {
			Name        string `json:"name"`
			Description string `json:"description"`
		} `json:"tools"`
	}
	if err := json.Unmarshal(toolsRes, &toolsObj); err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: tools/list ilegible: %v\n", err)
		os.Exit(1)
	}

	fichaRes, err := c.call("resources/read", map[string]any{"uri": "android://tool/" + *tool})
	if err != nil {
		fmt.Fprintf(os.Stderr, "jav-tokens: resources/read(%s) falló: %v\n", *tool, err)
		os.Exit(1)
	}
	fichaText := resourceText(fichaRes)

	// Carga cognitiva = instructions + Σ descripciones (lo que audit-mcp mide
	// como bytes/4). Se tokeniza por separado para poder comparar plano a plano.
	var descTotal strings.Builder
	descTotal.WriteString(initObj.Instructions)
	for _, t := range toolsObj.Tools {
		descTotal.WriteString("\n")
		descTotal.WriteString(t.Description)
	}

	s := stats{
		instructions:      count(initObj.Instructions),
		toolsList:         count(string(toolsRes)),
		cognitive:         count(descTotal.String()),
		ficha:             count(fichaText),
		toolCount:         len(toolsObj.Tools),
		instructionsLen:   len(initObj.Instructions),
		instructionsWords: words(initObj.Instructions),
		toolsListLen:      len(toolsRes),
		cognitiveLen:      len(descTotal.String()),
		fichaLen:          len(fichaText),
	}
	s.total = s.instructions + s.toolsList

	report(s, *tool, *encoding)
}

// resourceText concatena el campo text de las contents de resources/read.
func resourceText(raw json.RawMessage) string {
	var obj struct {
		Contents []struct {
			Text string `json:"text"`
		} `json:"contents"`
	}
	if err := json.Unmarshal(raw, &obj); err != nil {
		return ""
	}
	var b strings.Builder
	for _, c := range obj.Contents {
		b.WriteString(c.Text)
	}
	return b.String()
}

func words(s string) int { return len(strings.Fields(s)) }

func report(s stats, tool, encoding string) {
	const baselineAudit = 1631 // bytes/4 medido por audit-mcp (v1.2.0); carga cognitiva
	pctDelta := 0.0
	if baselineAudit > 0 {
		pctDelta = (float64(s.cognitive-baselineAudit) / float64(baselineAudit)) * 100
	}
	flag20 := "OK"
	if pctDelta > 20 || pctDelta < -20 {
		flag20 = "DESVÍO >20% vs audit-mcp → revisar CompactDesc"
	}

	fmt.Printf("jav-tokens — encoding=%s\n", encoding)
	fmt.Printf("instructions: %d palabras → %d tokens (%d bytes)\n", s.instructionsWords, s.instructions, s.instructionsLen)
	fmt.Printf("tools/list: %d tools → %d tokens (%d bytes, payload completo)\n", s.toolCount, s.toolsList, s.toolsListLen)
	fmt.Printf("carga cognitiva (instructions+Σdesc): %d tokens (%d bytes)\n", s.cognitive, s.cognitiveLen)
	fmt.Printf("ficha individual (%s): %d tokens (%d bytes)\n", tool, s.ficha, s.fichaLen)
	fmt.Printf("total arranque (instructions+tools/list): %d tokens\n", s.total)
	fmt.Printf("objetivo ≤3000 tokens (carga cognitiva): %s\n", map[bool]string{true: "✅", false: "❌"}[s.cognitive <= 3000])
	fmt.Printf("audit-mcp (bytes/4, carga cognitiva): %d tokens → Δ %+.1f%% [%s]\n", baselineAudit, pctDelta, flag20)
	fmt.Println("nota: el payload completo incluye el esquema MCP fijo (no reducible sin romper el contrato).")
}
