package main

// unixsock.go — Unix domain socket IPC (spec v2 §5).
// Replaces the TCP loopback send API; socket lives in STORE_DIR with 0600.

import (
	"net"
	"os"
	"path/filepath"
)

// SocketName is the single IPC socket filename.
const SocketName = "bridge.sock"

// SocketPath joins the store dir with the socket name.
func SocketPath(storeDir string) string {
	return filepath.Join(storeDir, SocketName)
}

// ListenUnixSocket removes any stale socket and listens with owner-only perms.
func ListenUnixSocket(storeDir string) (net.Listener, error) {
	path := SocketPath(storeDir)
	_ = os.Remove(path)
	lc := net.ListenConfig{}
	ln, err := lc.Listen(nil, "unix", path)
	if err != nil {
		return nil, err
	}
	if err := os.Chmod(path, 0600); err != nil {
		ln.Close()
		return nil, err
	}
	return ln, nil
}
