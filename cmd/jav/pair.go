package main

import (
	"fmt"
	"os"

	"github.com/k4wai1/jav/pkg/jam"
)

// runPair implementa `jav pair <ip-o-url> <token> [openrouter_api_key]`:
// vincula el binario con el teléfono en un paso (hello + Auto-TOFU +
// `~/.config/jav/config.json`) **sin reiniciar el cliente MCP**.
//
// Este archivo ES el contrato CLI de `jav pair` (stdout = mensaje de
// vinculación) y NO forma parte del servidor MCP: `cmd/audit-mcp` lo
// excluye del scan `no-stdout-statico` a propósito (ver auditoría).
func runPair(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "uso: jav pair <ip-o-url> <token> [openrouter_api_key]")
		fmt.Fprintln(os.Stderr, "ej.: jav pair 100.105.124.102 <token>   # WSS tailnet (Auto-TOFU)")
		fmt.Fprintln(os.Stderr, "     jav pair usb <token>               # loopback por adb forward")
		return 2
	}
	addr, token := args[0], args[1]

	res, err := jam.Pair(addr, token)
	if err != nil {
		fmt.Fprintf(os.Stderr, "✗ vinculación falló: %v\n", err)
		return 1
	}
	if len(args) >= 3 && args[2] != "" {
		if err := jam.UpdateConfig(func(c *jam.Config) { c.OpenRouterAPIKey = args[2] }); err != nil {
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
