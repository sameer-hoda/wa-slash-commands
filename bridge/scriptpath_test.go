package main

// Durable coverage: the bundled app sets PY_SCRIPTS_DIR; the bridge must
// look there FIRST. Without this, mechat/gemini helpers silently never run
// (unknown number, phantom "invalid" key).

import (
	"os"
	"path/filepath"
	"testing"
)

func TestScriptSearchDirsPrefersEnv(t *testing.T) {
	t.Setenv("PY_SCRIPTS_DIR", "/tmp/fake-scripts")
	dirs := scriptSearchDirs()
	if len(dirs) == 0 || dirs[0] != "/tmp/fake-scripts" {
		t.Fatalf("PY_SCRIPTS_DIR must be first, got %v", dirs)
	}
}

func TestScriptSearchDirsWithoutEnv(t *testing.T) {
	os.Unsetenv("PY_SCRIPTS_DIR")
	dirs := scriptSearchDirs()
	if len(dirs) == 0 || dirs[0] != "." {
		t.Fatalf("without env, CWD must be first, got %v", dirs)
	}
}

func TestFindScriptUsesEnvDir(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "probe.py"), []byte("x"), 0644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PY_SCRIPTS_DIR", dir)
	got := findScript("probe.py")
	if got != filepath.Join(dir, "probe.py") {
		t.Fatalf("expected env-dir script, got %q", got)
	}
}
