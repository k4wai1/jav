package jam

import (
	"context"
	"net"
	"net/http"
	"os"
	"time"
)

// Cliente HTTP de las llamadas a la IA (S1/S2) con resolver DNS explícito
// cuando el SO no expone `/etc/resolv.conf`. En Android/Termux con
// `CGO_ENABLED=0` el resolver puro de Go consulta `[::1]:53` y falla con
// `lookup openrouter.ai on [::1]:53: connection refused`; aquí se apunta a
// servidores públicos (Cloudflare/Google) por UDP/TCP directo.

// dnsServers resolvers de fallback para Android/Termux (sin resolv.conf).
var dnsServers = []string{"1.1.1.1:53", "8.8.8.8:53"}

// resolvConfMissing informa si el SO no tiene `/etc/resolv.conf` (Android).
func resolvConfMissing() bool {
	_, err := os.Stat("/etc/resolv.conf")
	return err != nil
}

// needsExplicitDNS: dentro del teléfono o sin resolv.conf.
func needsExplicitDNS() bool {
	return isAndroidOrTermux() || resolvConfMissing()
}

// HTTPClient cliente HTTP con timeout de marcado y resolver resiliente.
// Los timeouts por petición los ponen los callers vía `context`.
var HTTPClient = newHTTPClient()

func newHTTPClient() *http.Client {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	if needsExplicitDNS() {
		dialer.Resolver = &net.Resolver{
			PreferGo: true,
			Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
				var lastErr error
				for _, srv := range dnsServers {
					conn, err := (&net.Dialer{Timeout: 5 * time.Second}).
						DialContext(ctx, network, srv)
					if err == nil {
						return conn, nil
					}
					lastErr = err
				}
				return nil, lastErr
			},
		}
	}
	return &http.Client{
		Transport: &http.Transport{
			Proxy:               http.ProxyFromEnvironment,
			DialContext:         dialer.DialContext,
			ForceAttemptHTTP2:   true,
			MaxIdleConns:        20,
			IdleConnTimeout:     90 * time.Second,
			TLSHandshakeTimeout: 10 * time.Second,
		},
	}
}
