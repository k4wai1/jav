package jam

import (
	"testing"
)

func TestEnvFallback(t *testing.T) {
	t.Setenv("JAV_WS_URL", "")
	t.Setenv("JEV_WS_URL", "ws://10.0.0.1:38472/")
	if WSURL() != "ws://10.0.0.1:38472/" {
		t.Fatalf("fallback JEV_WS_URL: %s", WSURL())
	}
	t.Setenv("JEV_WS_URL", "")
	if WSURL() != "ws://127.0.0.1:38472/" {
		t.Fatalf("default loopback: %s", WSURL())
	}
	t.Setenv("JAV_TOKEN", "")
	t.Setenv("JEV_TOKEN", "abc")
	tok, jerr := Token()
	if jerr != nil || tok != "abc" {
		t.Fatalf("fallback JEV_TOKEN: %q %v", tok, jerr)
	}
	t.Setenv("JEV_TOKEN", "")
	if _, jerr := Token(); jerr == nil || jerr.Code != "UNAUTHORIZED" {
		t.Fatalf("sin token debe ser UNAUTHORIZED honesto: %v", jerr)
	}
}

func TestDialWithoutTokenFailsHonest(t *testing.T) {
	t.Setenv("JAV_TOKEN", "")
	t.Setenv("JEV_TOKEN", "")
	if _, jerr := Dial(); jerr == nil || jerr.Code != "UNAUTHORIZED" {
		t.Fatalf("dial sin token: %v", jerr)
	}
}
