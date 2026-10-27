package main

// gemini_check.py exits nonzero by design (0 valid / 1 missing / 2 invalid),
// so a nonzero exit with clean stdout is a REAL answer, not a failure.
// Only garbage/empty output means "invalid".

import "testing"

func TestClassifyGeminiOutput(t *testing.T) {
	cases := map[string]string{
		"valid":   "valid",
		"invalid": "invalid",
		"missing": "missing",
		"":        "invalid",
		"weird!":  "invalid",
	}
	for in, want := range cases {
		if got := classifyGeminiOutput(in); got != want {
			t.Errorf("classifyGeminiOutput(%q) = %q, want %q", in, got, want)
		}
	}
}
