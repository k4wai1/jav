package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/k4wai1/jav/pkg/jam"
)

// runPair implementa `jav pair [ip-o-url] [token] [openrouter_api_key]`:
// vincula el binario con el teléfono en un paso (hello + Auto-TOFU +
// `~/.config/jav/config.json`) **sin reiniciar el cliente MCP**.
//
// Modos:
//   - `jav pair <ip-o-url> <token> [key]`  no interactivo (scripts/CI).
//   - `jav pair <ip-o-url>`                pide solo el token por stdin.
//   - `jav pair`                           interactivo (pide ip y token).
//
// La entrada interactiva solo se activa si stdin es una terminal; si no hay
// args y stdin está pipeado (script), se imprime el uso y se sale 2 (nunca
// queda colgado esperando EOF).
//
// Este archivo ES el contrato CLI de `jav pair` (stdout = mensaje de
// vinculación) y NO forma parte del servidor MCP: `cmd/audit-mcp` lo
// excluye del scan `no-stdout-statico` a propósito (ver auditoría).
func runPair(args []string) int {
	addr, token, key, ok := parsePairArgs(args)
	if !ok {
		return 2
	}

	res, err := jam.Pair(addr, token)
	if err != nil {
		fmt.Fprintf(os.Stderr, "✗ vinculación falló: %v\n", err)
		return 1
	}
	if key != "" {
		if err := jam.UpdateConfig(func(c *jam.Config) { c.OpenRouterAPIKey = key }); err != nil {
			fmt.Fprintf(os.Stderr, "⚠ no pude guardar openrouter_api_key: %v\n", err)
		}
	}

	dev := res.Model
	if dev == "" {
		dev = res.Device
	}
	if dev == "" {
		dev = "dispositivo"
	}
	fp := res.Fingerprint
	if len(fp) > 16 {
		fp = fp[:16]
	}
	if fp != "" {
		fmt.Printf("✓ Vinculado con %s %s (SDK %d) en %s [TOFU sha256: %s…]\n",
			res.Manufacturer, dev, res.SDK, res.URL, fp)
	} else {
		fmt.Printf("✓ Vinculado con %s %s (SDK %d) en %s\n",
			res.Manufacturer, dev, res.SDK, res.URL)
	}
	fmt.Printf("  config: %s (0600)\n", jam.ConfigPath())
	fmt.Println(`  listo: registra "command": ["jav"] en tu cliente MCP (sin variables de entorno)`)
	return 0
}

// parsePairArgs resuelve (addr, token, openrouter_key) desde los args,
// completando por stdin en modo interactivo. ok=false → ya se imprimió el
// error/uso y el llamador debe salir con 2.
func parsePairArgs(args []string) (addr, token, key string, ok bool) {
	// Modo no interactivo (≥2 args): comportamiento histórico intacto.
	if len(args) >= 2 {
		addr, token = args[0], args[1]
		if len(args) >= 3 {
			key = args[2]
		}
		return addr, token, key, true
	}

	// A partir de aquí hace falta stdin interactivo.
	if !isTTY(os.Stdin) {
		pairUsage()
		return "", "", "", false
	}
	in := bufio.NewReader(os.Stdin)

	switch len(args) {
	case 0:
		a, err := promptLine(in, `IP o alias del teléfono (o "usb"): `)
		if err != nil {
			return "", "", "", false
		}
		addr = a
	case 1:
		addr = args[0]
	}
	if addr == "" {
		fmt.Fprintln(os.Stderr, "✗ falta la IP (o \"usb\")")
		return "", "", "", false
	}

	t, err := promptLine(in, "Token (pégalo de la app): ")
	if err != nil {
		return "", "", "", false
	}
	token = t
	if token == "" {
		fmt.Fprintln(os.Stderr, "✗ falta el token")
		return "", "", "", false
	}
	return addr, token, "", true
}

// promptLine imprime el prompt y devuelve la línea sin espacios extremos.
func promptLine(in *bufio.Reader, prompt string) (string, error) {
	fmt.Print(prompt)
	line, err := in.ReadString('\n')
	if err != nil && line == "" {
		fmt.Fprintln(os.Stderr)
		fmt.Fprintf(os.Stderr, "✗ no pude leer la entrada: %v\n", err)
		return "", err
	}
	return strings.TrimSpace(line), nil
}

// isTTY reporta si f es una terminal (para decidir el modo interactivo).
func isTTY(f *os.File) bool {
	fi, err := f.Stat()
	if err != nil {
		return false
	}
	return fi.Mode()&os.ModeCharDevice != 0
}

func pairUsage() {
	fmt.Fprintln(os.Stderr, "uso: jav pair [ip-o-url] [token] [openrouter_api_key]")
	fmt.Fprintln(os.Stderr, "  jav pair                            # interactivo (pide ip y token)")
	fmt.Fprintln(os.Stderr, "ej.: jav pair 100.105.124.102 <token> # WSS tailnet (Auto-TOFU)")
	fmt.Fprintln(os.Stderr, "     jav pair usb <token>             # loopback por adb forward")
}
