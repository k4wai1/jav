package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/k4wai1/jav/pkg/jam"
)

// runPair implementa `jav pair [ip-o-url] [token] [openrouter_api_key]`:
// vincula el binario con el teléfono en un paso (hello + Auto-TOFU +
// `~/.config/jav/config.json`) **sin reiniciar el cliente MCP**.
//
// Modos:
//   - `jav pair <ip-o-url> <token> [key]`  no interactivo (scripts/CI).
//   - `jav pair --name <alias> …`          vincula bajo un alias explícito.
//   - `jav pair auto <token>`              descubre por mDNS en la LAN.
//   - `jav pair --list` / `list`           lista dispositivos vinculados.
//   - `jav pair --use <alias>` / `use …`   cambia el dispositivo activo.
//   - `jav pair <ip-o-url>`                pide solo el token por stdin.
//   - `jav pair`                           interactivo (descubre mDNS y pide ip/token).
//
// La entrada interactiva solo se activa si stdin es una terminal; si no hay
// args y stdin está pipeado (script), se imprime el uso y se sale 2 (nunca
// queda colgado esperando EOF).
//
// Este archivo ES el contrato CLI de `jav pair` (stdout = mensaje de
// vinculación) y NO forma parte del servidor MCP: `cmd/audit-mcp` lo
// excluye del scan `no-stdout-statico` a propósito (ver auditoría).
func runPair(args []string) int {
	if code, handled := pairManagement(args); handled {
		return code
	}
	name, rest, ok := extractNameFlag(args)
	if !ok {
		return 2
	}
	addr, token, key, ok := parsePairArgs(rest)
	if !ok {
		return 2
	}
	if isAutoAddr(addr) {
		resolved, code := resolveAutoAddr()
		if code != 0 {
			return code
		}
		addr = resolved
	}

	res, err := jam.PairNamed(name, addr, token)
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
		fmt.Printf("✓ Vinculado con %s %s (SDK %d) en %s [alias: %s] [TOFU sha256: %s…]\n",
			res.Manufacturer, dev, res.SDK, res.URL, res.Alias, fp)
	} else {
		fmt.Printf("✓ Vinculado con %s %s (SDK %d) en %s [alias: %s]\n",
			res.Manufacturer, dev, res.SDK, res.URL, res.Alias)
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
		// v2.1.0: descubre por mDNS; v2.3.0: selección por número 1..N.
		def := ""
		devs := jam.DiscoverMDNS(jam.DefaultMDNSTimeout)
		if len(devs) > 0 {
			fmt.Println("dispositivos Jav en la LAN (mDNS):")
			for i, d := range devs {
				fmt.Printf("  %d) %s  %s:%d\n", i+1, d.Name, d.IP, d.Port)
			}
			def = devs[0].IP
		}
		label := `IP, alias o número ("auto" / "usb")`
		if def != "" {
			label += " [" + def + "]"
		}
		a, err := promptLine(in, label+": ")
		if err != nil {
			return "", "", "", false
		}
		if a == "" {
			a = def
		}
		if n, err := strconv.Atoi(a); err == nil {
			if n < 1 || n > len(devs) {
				fmt.Fprintf(os.Stderr, "✗ número fuera de rango (1..%d)\n", len(devs))
				return "", "", "", false
			}
			a = devs[n-1].IP
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

// isAutoAddr reconoce los alias de autodescubrimiento mDNS.
func isAutoAddr(addr string) bool {
	switch strings.ToLower(strings.TrimSpace(addr)) {
	case "auto", "mdns", "discover", "scan":
		return true
	}
	return false
}

// resolveAutoAddr busca por mDNS (ventana ~800 ms) y devuelve una URL WSS.
// 0 dispositivos o varios → mensaje honesto y exit 1 (no se adivina).
func resolveAutoAddr() (string, int) {
	devs := jam.DiscoverMDNS(jam.DefaultMDNSTimeout)
	switch len(devs) {
	case 0:
		fmt.Fprintln(os.Stderr, "✗ mDNS: no encontré ningún Jav (_jav-mcp._tcp) en la LAN")
		fmt.Fprintln(os.Stderr, "  usa la IP manual: jav pair <ip> <token> (la app muestra las URLs WSS)")
		return "", 1
	case 1:
		d := devs[0]
		fmt.Fprintf(os.Stderr, "→ mDNS: %s en %s:%d\n", d.Name, d.IP, d.Port)
		return fmt.Sprintf("wss://%s:%d/", d.IP, d.Port), 0
	default:
		fmt.Fprintln(os.Stderr, "✗ mDNS: varios dispositivos; indica la IP explícita:")
		for _, d := range devs {
			fmt.Fprintf(os.Stderr, "    %-20s %s:%d\n", d.Name, d.IP, d.Port)
		}
		return "", 1
	}
}

// pairManagement atiende los comandos de gestión multidispositivo:
//
//	jav pair --list | list
//	jav pair --use <alias> | use <alias>
//	jav pair --remove <alias> | rm <alias> | unpair <alias>
func pairManagement(args []string) (int, bool) {
	if len(args) == 0 {
		return 0, false
	}
	switch args[0] {
	case "--list", "list":
		return pairList(), true
	case "--use", "use":
		if len(args) < 2 || strings.TrimSpace(args[1]) == "" {
			fmt.Fprintln(os.Stderr, "✗ uso: jav pair --use <alias>   (lista: jav pair --list)")
			return 2, true
		}
		return pairUse(args[1]), true
	case "--remove", "rm", "unpair":
		if len(args) < 2 || strings.TrimSpace(args[1]) == "" {
			fmt.Fprintln(os.Stderr, "✗ uso: jav pair --remove <alias>   (lista: jav pair --list)")
			return 2, true
		}
		return pairRemove(args[1]), true
	}
	return 0, false
}

// pairList imprime los dispositivos vinculados (marca el activo con `*`).
func pairList() int {
	devs := jam.PairedDevices()
	names := jam.PairedDeviceNames()
	if len(names) == 0 {
		fmt.Println("sin dispositivos vinculados")
		return 0
	}
	active := jam.ActiveDeviceName()
	for _, n := range names {
		d := devs[n]
		mark := "  "
		if n == active {
			mark = "* "
		}
		model := d.Model
		if model == "" {
			model = d.Device
		}
		if model == "" {
			model = "—"
		}
		fmt.Printf("%s%s  %s (SDK %d)  %s\n", mark, n, model, d.SDK, d.WSURL)
	}
	return 0
}

// pairUse cambia el dispositivo activo y confirma por stdout.
func pairUse(alias string) int {
	d, err := jam.SelectDevice(alias)
	if err != nil {
		fmt.Fprintf(os.Stderr, "✗ %v\n", err)
		return 1
	}
	fmt.Printf("✓ dispositivo activo: %s  %s\n", jam.ActiveDeviceName(), d.WSURL)
	return 0
}

// pairRemove desvincula un dispositivo; si era el activo, promociona otro.
func pairRemove(alias string) int {
	next, err := jam.RemoveDevice(alias)
	if err != nil {
		fmt.Fprintf(os.Stderr, "✗ %v\n", err)
		return 1
	}
	if next == "" {
		fmt.Printf("✓ dispositivo %q desvinculado; sin dispositivos activos\n", alias)
	} else {
		fmt.Printf("✓ dispositivo %q desvinculado; activo: %s\n", alias, next)
	}
	return 0
}

// extractNameFlag saca `--name <alias>` / `-n <alias>` (o `--name=a`) de
// los args antes del parser posicional. Un flag sin valor → error + uso.
func extractNameFlag(args []string) (name string, rest []string, ok bool) {
	rest = make([]string, 0, len(args))
	for i := 0; i < len(args); i++ {
		switch a := args[i]; {
		case a == "--name" || a == "-n":
			if i+1 >= len(args) || strings.TrimSpace(args[i+1]) == "" {
				fmt.Fprintf(os.Stderr, "✗ %s requiere un alias no vacío\n", a)
				pairUsage()
				return "", nil, false
			}
			name = strings.TrimSpace(args[i+1])
			i++
		case strings.HasPrefix(a, "--name="):
			name = strings.TrimSpace(strings.TrimPrefix(a, "--name="))
			if name == "" {
				fmt.Fprintln(os.Stderr, "✗ --name= requiere un alias no vacío")
				pairUsage()
				return "", nil, false
			}
		default:
			rest = append(rest, a)
		}
	}
	return name, rest, true
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
	fmt.Fprintln(os.Stderr, "uso: jav pair [--name <alias>] [ip-o-url|auto] [token] [openrouter_api_key]")
	fmt.Fprintln(os.Stderr, "     jav pair --list | list           # dispositivos vinculados (* = activo)")
	fmt.Fprintln(os.Stderr, "     jav pair --use <alias> | use …   # cambia el dispositivo activo")
	fmt.Fprintln(os.Stderr, "     jav pair --remove <alias> | rm … # desvincula (promociona otro activo)")
	fmt.Fprintln(os.Stderr, "  jav pair                            # interactivo (mDNS 1..N + ip/token)")
	fmt.Fprintln(os.Stderr, "ej.: jav pair auto <token>            # descubre por mDNS (_jav-mcp._tcp)")
	fmt.Fprintln(os.Stderr, "     jav pair --name pixel 100.105.124.102 <token>  # WSS tailnet")
	fmt.Fprintln(os.Stderr, "     jav pair 192.168.1.40 <token>    # WSS LAN Wi-Fi (Auto-TOFU)")
	fmt.Fprintln(os.Stderr, "     jav pair usb <token>             # loopback por adb forward")
}
