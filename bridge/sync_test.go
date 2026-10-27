package main

// Durable coverage: the Focus "syncing chats" loader bar may only play
// while history is actually arriving. A poll-driven heartbeat must never
// pin it on, and a long-quiet session must read as synced.

import (
	"testing"
	"time"
)

func TestChatSyncing(t *testing.T) {
	now := time.Now()
	recent := now.Add(-30 * time.Second).Unix()
	quiet := now.Add(-10 * time.Minute).Unix()
	oldPair := now.Add(-time.Hour).Unix()

	cases := []struct {
		name       string
		paired     bool
		pairedAt   int64
		lastWrite  int64
		want       bool
	}{
		{"unpaired never syncs", false, 0, 0, false},
		{"just paired, nothing yet", true, 0, 0, true},
		{"history arriving", true, recent, recent, true},
		{"quiet for minutes", true, quiet, quiet, false},
		{"old pairing, fresh write still synced", true, oldPair, recent, false},
		{"never any write after long pair", true, oldPair, 0, false},
	}
	for _, c := range cases {
		if got := chatSyncing(c.paired, c.pairedAt, c.lastWrite, now); got != c.want {
			t.Errorf("%s: chatSyncing = %v, want %v", c.name, got, c.want)
		}
	}
}

func TestNoteStoreWriteProgress(t *testing.T) {
	syncPairedAt.Store(0)
	syncLastWrite.Store(0)
	before := syncStoredMsgs.Load()
	noteStoreWrite()
	if syncPairedAt.Load() == 0 || syncLastWrite.Load() == 0 {
		t.Fatal("noteStoreWrite must stamp pairedAt and lastWrite")
	}
	first := syncPairedAt.Load()
	noteStoreWrite()
	if syncPairedAt.Load() != first {
		t.Fatal("pairedAt must stick at first pairing, not float")
	}
	if got := syncStoredMsgs.Load(); got != before {
		t.Fatalf("noteStoreWrite must not count messages itself, got delta %d", got-before)
	}
}
