package main

// events.go — Mac shell event stream (spec v2 §5).
// The Swift supervisor reads JSON lines on stdout:
// {"type":"qr|scanned|connected|logged_out|heartbeat|command|answer","payload":{...}}.

import (
	"encoding/json"
	"fmt"
	"time"
)

// Allowed event types (mirror mac/ipc/protocol.py EVENT_TYPES).
var allowedEventTypes = map[string]bool{
	"qr":         true,
	"scanned":    true,
	"connected":  true,
	"logged_out": true,
	"heartbeat":  true,
	"command":    true,
	"answer":     true,
}

// bridgeEvent is the stdout wire shape.
type bridgeEvent struct {
	Type    string         `json:"type"`
	Payload map[string]any `json:"payload"`
}

// EmitEvent writes one JSON line to stdout. Returns an error on unknown type.
func EmitEvent(eventType string, payload map[string]any) error {
	if !allowedEventTypes[eventType] {
		return fmt.Errorf("unknown event type: %s", eventType)
	}
	if payload == nil {
		payload = map[string]any{}
	}
	line, err := json.Marshal(bridgeEvent{Type: eventType, Payload: payload})
	if err != nil {
		return err
	}
	fmt.Println(string(line))
	return nil
}

// EmitHeartbeat is the ~30s supervisor ping body.
func EmitHeartbeat() error {
	return EmitEvent("heartbeat", map[string]any{"at": time.Now().UTC().Format(time.RFC3339)})
}
