package main

// Durable coverage: the Gemini key is Keychain-only on the Mac and reaches
// the bridge as a process-environment value. The bridge must NEVER persist
// it to disk — no gemini_key file, no file fallback in pythonEnv.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestResolveGeminiKeyPrecedence(t *testing.T) {
	t.Setenv("GEMINI_API_KEY", "env-key")
	noteValidatedKey("live-key")
	t.Cleanup(func() { noteValidatedKey("") })
	if got := resolveGeminiKey("explicit-key"); got != "explicit-key" {
		t.Fatalf("explicit key must win, got %q", got)
	}
	if got := resolveGeminiKey(""); got != "live-key" {
		t.Fatalf("validated in-memory key must beat env, got %q", got)
	}
	noteValidatedKey("")
	if got := resolveGeminiKey(""); got != "env-key" {
		t.Fatalf("env key must be the last resort, got %q", got)
	}
}

func TestPythonEnvNeverReadsKeyFile(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("STORE_DIR", dir)
	// A legacy plaintext file must be ignored even when no env key exists.
	os.Unsetenv("GEMINI_API_KEY")
	sentinel := filepath.Join(dir, "gemini_key")
	if err := os.WriteFile(sentinel, []byte("sentinel-legacy-key"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, e := range pythonEnv() {
		if strings.HasPrefix(e, "GEMINI_API_KEY=") {
			t.Fatalf("pythonEnv leaked a key from disk: %q", e)
		}
	}
}

// Regression: geminiKeyStatus must never hold geminiMu across checkGeminiKey
// (Go mutexes are not reentrant — that deadlocks every /setup/state poll).
func TestGeminiKeyStatusDoesNotDeadlock(t *testing.T) {
	t.Setenv("STORE_DIR", t.TempDir())
	os.Unsetenv("GEMINI_API_KEY")
	noteValidatedKey("")
	resetGeminiCache()
	done := make(chan string, 1)
	go func() { done <- geminiKeyStatus() }()
	select {
	case s := <-done:
		t.Logf("status=%q", s)
	case <-time.After(20 * time.Second):
		t.Fatal("geminiKeyStatus hung — probable geminiMu re-entrant deadlock")
	}
}

func TestPythonEnvUsesLiveKeyBeforeRelaunch(t *testing.T) {
	t.Setenv("STORE_DIR", t.TempDir())
	os.Unsetenv("GEMINI_API_KEY")
	noteValidatedKey("just-validated")
	t.Cleanup(func() { noteValidatedKey("") })
	found := false
	for _, e := range pythonEnv() {
		if e == "GEMINI_API_KEY=just-validated" {
			found = true
		}
	}
	if !found {
		t.Fatal("pythonEnv must carry the just-validated in-memory key")
	}
}

func TestPythonEnvForwardsSupervisorKey(t *testing.T) {
	t.Setenv("STORE_DIR", t.TempDir())
	t.Setenv("GEMINI_API_KEY", "supervisor-key")
	found := false
	for _, e := range pythonEnv() {
		if e == "GEMINI_API_KEY=supervisor-key" {
			found = true
		}
	}
	if !found {
		t.Fatal("pythonEnv must forward the Supervisor-provided env key")
	}
}
