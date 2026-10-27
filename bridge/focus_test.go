package main

// Durable coverage: the Focus UI contract. /focus/top10 serves the cached
// digest byte-for-byte (404 before the first ranking); /focus/done records
// app-side done-marks into done.json for the next ranking pass.

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestServeFocusDigestPassthrough(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("STORE_DIR", dir)
	body := `{"generated_at":"2026-10-27T19:45:00+05:30","headline":"x","items":[]}`
	if err := os.WriteFile(filepath.Join(dir, "focus.json"), []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodGet, "/focus/top10", nil)
	rec := httptest.NewRecorder()
	serveFocusDigest(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	if strings.TrimSpace(rec.Body.String()) != body {
		t.Fatalf("body drifted: %q", rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("content-type = %q", ct)
	}
}

func TestServeFocusDigestMissing(t *testing.T) {
	t.Setenv("STORE_DIR", t.TempDir())
	req := httptest.NewRequest(http.MethodGet, "/focus/top10", nil)
	rec := httptest.NewRecorder()
	serveFocusDigest(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
}

func TestServeFocusDigestReasonPassthrough(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("STORE_DIR", dir)
	errBody := `{"reason":"no-chats","detail":"no-chats: nothing recent","at":"2026-10-27T20:00:00+05:30"}`
	if err := os.WriteFile(filepath.Join(dir, "focus_error.json"), []byte(errBody), 0600); err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodGet, "/focus/top10", nil)
	rec := httptest.NewRecorder()
	serveFocusDigest(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
	body := rec.Body.String()
	if !strings.Contains(body, `"reason":"no-chats"`) {
		t.Fatalf("reason missing from 404 body: %s", body)
	}
	if !strings.Contains(body, "No recent chats to rank yet") {
		t.Fatalf("human text missing from 404 body: %s", body)
	}
}

func TestHandleFocusDoneRequiresID(t *testing.T) {
	t.Setenv("STORE_DIR", t.TempDir())
	req := httptest.NewRequest(http.MethodPost, "/focus/done", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	handleFocusDone(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}

func TestHandleFocusDoneWritesDoneJSON(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("STORE_DIR", dir)
	req := httptest.NewRequest(http.MethodPost, "/focus/done",
		strings.NewReader(`{"id":"abc123","title":"Send deck","chat_jid":"g@g.us","last_activity":"2026-10-27T18:00:00+05:30"}`))
	rec := httptest.NewRecorder()
	handleFocusDone(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body %q", rec.Code, rec.Body.String())
	}
	raw, err := os.ReadFile(filepath.Join(dir, "done.json"))
	if err != nil {
		t.Fatalf("done.json not written: %v", err)
	}
	if !strings.Contains(string(raw), "abc123") {
		t.Fatalf("done.json missing id: %s", raw)
	}
}
