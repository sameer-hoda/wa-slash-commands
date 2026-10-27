package main

// Durable coverage: local Mac mode must skip the setup-password gate and
// bind loopback only. A regression here re-locks the user out with an
// unfindable generated password.

import (
	"os"
	"testing"
)

func TestNoAuthModeDefaultsOff(t *testing.T) {
	os.Unsetenv("SETUP_NO_AUTH")
	if noAuthMode() {
		t.Fatal("noAuthMode should default to false")
	}
}

func TestNoAuthModeEnabled(t *testing.T) {
	t.Setenv("SETUP_NO_AUTH", "1")
	if !noAuthMode() {
		t.Fatal("noAuthMode should be true when SETUP_NO_AUTH=1")
	}
}

func TestSetupBindAddrIsLoopbackOnly(t *testing.T) {
	addr := setupBindAddr("8081")
	if addr != "127.0.0.1:8081" {
		t.Fatalf("setup must bind loopback only, got %q", addr)
	}
}
