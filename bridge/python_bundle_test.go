package main

// Durable coverage: the shipped app must use its own Python, never the
// tester's. bundlePython derives Resources/python-runtime from the running
// binary; outside an .app it yields "" and is skipped.

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCandidatesNeverEmpty(t *testing.T) {
	os.Unsetenv("MOSAIC_PYTHON")
	for _, c := range pythonCandidates() {
		if c == "" {
			t.Fatal("pythonCandidates must not contain empty entries")
		}
	}
}

func TestBundlePythonOutsideApp(t *testing.T) {
	// go test binaries never live in Contents/MacOS.
	if got := bundlePython(); got != "" {
		t.Fatalf("expected empty outside a bundle, got %q", got)
	}
}

func TestBundlePythonLayout(t *testing.T) {
	dir := t.TempDir()
	macos := filepath.Join(dir, "Contents", "MacOS")
	if err := os.MkdirAll(macos, 0755); err != nil {
		t.Fatal(err)
	}
	bin := filepath.Join(dir, "Contents", "Resources", "python-runtime", "bin")
	if err := os.MkdirAll(bin, 0755); err != nil {
		t.Fatal(err)
	}
	want := filepath.Join(bin, "python3")
	if err := os.WriteFile(want, []byte("x"), 0755); err != nil {
		t.Fatal(err)
	}
	if got := bundlePythonFrom(filepath.Join(macos, "Mosaic")); got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
