package jam

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"math/big"
	"testing"
	"time"
)

// Fase 2b: el pin SHA-256 del cert del tailnet se normaliza (minúsculas,
// sin `:` ni espacios) desde JAV_CERT_FINGERPRINT / JEV_CERT_FINGERPRINT.
func TestCertFingerprintNormaliza(t *testing.T) {
	t.Setenv("JAV_CERT_FINGERPRINT", "AB:CD:Ef 01")
	t.Setenv("JEV_CERT_FINGERPRINT", "")
	if got := certFingerprint(); got != "abcdef01" {
		t.Fatalf("normalización: %s", got)
	}
	t.Setenv("JAV_CERT_FINGERPRINT", "")
	t.Setenv("JEV_CERT_FINGERPRINT", "11:22")
	if got := certFingerprint(); got != "1122" {
		t.Fatalf("fallback JEV: %s", got)
	}
}

// Fase 2b: WSS con TOFU — sin pin acepta; con pin correcto acepta; con pin
// distinto o sin certificado de servidor rechaza.
func TestPinnedTLSConfigTOFU(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "jam.local"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(cert.Raw)
	good := hex.EncodeToString(sum[:])
	cs := tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}}

	if err := pinnedTLSConfig("").VerifyConnection(cs); err != nil {
		t.Fatalf("TOFU sin pin debe pasar: %v", err)
	}
	if err := pinnedTLSConfig(good).VerifyConnection(cs); err != nil {
		t.Fatalf("pin correcto debe pasar: %v", err)
	}
	bad := "00" + good[2:]
	if err := pinnedTLSConfig(bad).VerifyConnection(cs); err == nil {
		t.Fatal("pin incorrecto debe fallar")
	}
	if err := pinnedTLSConfig(good).VerifyConnection(tls.ConnectionState{}); err == nil {
		t.Fatal("sin certificado de servidor debe fallar con pin")
	}
}
