package main

// Durable coverage: GUI-launched apps inherit a minimal PATH, so bare
// "python3" resolves to /usr/bin/python3 which lacks our deps. The bridge
// must pick an interpreter that can actually import them.

import (
	"os"
	"os/exec"
	"testing"
	"time"
)

func TestPythonCandidatesPreferOverride(t *testing.T) {
	t.Setenv("MOSAIC_PYTHON", "/tmp/custom-python")
	c := pythonCandidates()
	if len(c) == 0 || c[0] != "/tmp/custom-python" {
		t.Fatalf("MOSAIC_PYTHON must come first, got %v", c)
	}
}

func TestPythonCandidatesFallbackBare(t *testing.T) {
	os.Unsetenv("MOSAIC_PYTHON")
	c := pythonCandidates()
	if len(c) == 0 || c[len(c)-1] != "python3" {
		t.Fatalf("bare python3 must be last resort, got %v", c)
	}
}

func TestFindPythonResolves(t *testing.T) {
	got := findPython()
	if got == "" {
		t.Fatal("findPython must always return something")
	}
	if _, err := exec.LookPath(got); err != nil {
		// Bare "python3" relies on the caller's PATH; only absolute
		// paths must resolve here.
		if len(got) > 0 && got[0] == '/' {
			t.Fatalf("absolute python %q not executable: %v", got, err)
		}
	}
	_ = time.Second // keep time import if unused elsewhere
}
