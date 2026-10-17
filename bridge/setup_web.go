package main

// setup_web.go — launch layer for the slash-commands MVP:
//   * STORE_DIR-aware paths + bridge token for the internal API
//   * web setup page: QR (PNG data-URL, auto-refresh), Gemini-key tick,
//     connected view, Unlink — behind a setup password
//   * /health for Railway healthchecks
//   * python hooks: wacmd per /command, mechat.py --resolve --welcome at launch
//   * single source of truth for Me-chat state: store/mechat.json

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	_ "embed"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/mdp/qrterminal"
	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	waLog "go.mau.fi/whatsmeow/util/log"
)

//go:embed wizard.html
var wizardHTML string

const cookieName = "mosaic_setup"

var (
	setupPasswordHash []byte
	setupAuthSecret   []byte
	bridgeTokenVal    string

	qrMu             sync.Mutex
	currentQRDataURL string

	loginMu       sync.Mutex
	loginAttempts = map[string][]time.Time{}

	geminiMu        sync.Mutex
	geminiKeyCached string
	geminiCheckedAt time.Time

	resolveMu     sync.Mutex
	lastResolveAt time.Time
)

func storeDir() string {
	if dir := os.Getenv("STORE_DIR"); dir != "" {
		return dir
	}
	return "store"
}

func storePath(name string) string {
	return filepath.Join(storeDir(), name)
}

func absStorePath(name string) string {
	abs, err := filepath.Abs(storePath(name))
	if err != nil {
		return storePath(name)
	}
	return abs
}

func randomHex(n int) string {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("fallback-%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(buf)
}

func initAuth() {
	if err := os.MkdirAll(storeDir(), 0755); err != nil {
		fmt.Printf("store dir error: %v\n", err)
	}
	secret := sha256.Sum256([]byte(randomHex(32)))
	setupAuthSecret = secret[:]
	password := os.Getenv("SETUP_PASSWORD")
	generated := false
	if password == "" {
		password = randomHex(5)
		generated = true
	}
	sum := sha256.Sum256([]byte(password))
	setupPasswordHash = sum[:]
	if generated {
		fmt.Printf("\n╔══════════════════════════════════════════════╗\n")
		fmt.Printf("║  SETUP PASSWORD: %-27s ║\n", password)
		fmt.Printf("║  (set SETUP_PASSWORD env to choose your own) ║\n")
		fmt.Printf("╚══════════════════════════════════════════════╝\n\n")
	}
}

func initToken() {
	token := os.Getenv("BRIDGE_TOKEN")
	if token == "" {
		token = randomHex(12)
	}
	bridgeTokenVal = token
	if err := os.WriteFile(storePath("bridge_token"), []byte(token), 0600); err != nil {
		fmt.Printf("bridge token persist error: %v\n", err)
	}
}

func bridgeToken() string { return bridgeTokenVal }

func cookieValue() string {
	mac := hmac.New(sha256.New, setupAuthSecret)
	mac.Write([]byte("mosaic-setup-auth"))
	return hex.EncodeToString(mac.Sum(nil))
}

func validCookie(r *http.Request) bool {
	c, err := r.Cookie(cookieName)
	if err != nil {
		return false
	}
	return hmac.Equal([]byte(c.Value), []byte(cookieValue()))
}

func withAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !validCookie(r) {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"ok": false, "error": "auth required"})
			return
		}
		next(w, r)
	}
}

func requireToken(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		got := r.Header.Get("X-Bridge-Token")
		if subtle.ConstantTimeCompare([]byte(got), []byte(bridgeTokenVal)) != 1 {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"ok": false, "error": "invalid token"})
			return
		}
		next(w, r)
	}
}

func writeJSON(w http.ResponseWriter, code int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(payload)
}

func rateLimited(ip string) bool {
	loginMu.Lock()
	defer loginMu.Unlock()
	now := time.Now()
	kept := loginAttempts[ip][:0]
	for _, t := range loginAttempts[ip] {
		if now.Sub(t) < 5*time.Minute {
			kept = append(kept, t)
		}
	}
	loginAttempts[ip] = kept
	return len(kept) >= 5
}

func recordAttempt(ip string) {
	loginMu.Lock()
	defer loginMu.Unlock()
	loginAttempts[ip] = append(loginAttempts[ip], time.Now())
}

func handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"ok": false})
		return
	}
	ip := strings.Split(r.RemoteAddr, ":")[0]
	if rateLimited(ip) {
		writeJSON(w, http.StatusTooManyRequests, map[string]any{"ok": false, "error": "too many attempts"})
		return
	}
	var body struct {
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"ok": false})
		return
	}
	recordAttempt(ip)
	sum := sha256.Sum256([]byte(body.Password))
	if subtle.ConstantTimeCompare(sum[:], setupPasswordHash) != 1 {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"ok": false, "error": "wrong password"})
		return
	}
	http.SetCookie(w, &http.Cookie{
		Name: cookieName, Value: cookieValue(), Path: "/", HttpOnly: true,
		SameSite: http.SameSiteLaxMode, MaxAge: 60 * 60 * 24 * 30,
	})
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func serveWizard(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(wizardHTML))
}

// ── Me-chat state (single source of truth: store/mechat.json) ────────────────

type mechatState struct {
	JID      string  `json:"jid"`
	How      string  `json:"how"`
	Phone    string  `json:"phone"`
	Resolved float64 `json:"resolved_at"`
	Welcomed bool    `json:"welcomed"`
}

func readMechatState() mechatState {
	var state mechatState
	data, err := os.ReadFile(storePath("mechat.json"))
	if err != nil {
		return state
	}
	_ = json.Unmarshal(data, &state)
	return state
}

// ── Gemini key validity (cached 60 s, checked by gemini_check.py) ────────────

func geminiKeyStatus() string {
	geminiMu.Lock()
	defer geminiMu.Unlock()
	if time.Since(geminiCheckedAt) < time.Minute && geminiKeyCached != "" {
		return geminiKeyCached
	}
	status := "missing"
	cmd, err := pythonCmd("gemini_check.py")
	if err == nil {
		ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
		run := exec.CommandContext(ctx, cmd.Path, cmd.Args[1:]...)
		run.Env = cmd.Env
		out, err := run.Output()
		cancel()
		if err == nil {
			status = strings.TrimSpace(string(out))
			if status != "valid" && status != "invalid" && status != "missing" {
				status = "invalid"
			}
		} else {
			status = "invalid"
		}
	}
	geminiKeyCached = status
	geminiCheckedAt = time.Now()
	return status
}

// ── python bridge helpers ─────────────────────────────────────────────────────

func pythonEnv() []string {
	return append(os.Environ(),
		"BRIDGE_TOKEN="+bridgeTokenVal,
		"STORE_DIR="+absStorePath(""),
		"MESSAGES_DB_PATH="+absStorePath("messages.db"),
		"WHATSAPP_DB_PATH="+absStorePath("whatsapp.db"),
		"WA_API_URL=http://127.0.0.1:8090/api/send",
	)
}

func pythonCmd(name string, args ...string) (*exec.Cmd, error) {
	// Scripts may live at the app root, in scripts/, or one level up —
	// try the common locations so the bridge keeps working from any CWD.
	candidates := []string{
		name,
		filepath.Join("scripts", name),
		filepath.Join("..", name),
		filepath.Join("..", "scripts", name),
	}
	script := candidates[0]
	for _, cand := range candidates {
		if _, err := os.Stat(cand); err == nil {
			script = cand
			break
		}
	}
	abs, err := filepath.Abs(script)
	if err != nil {
		return nil, err
	}
	cmd := exec.Command("python3", append([]string{abs}, args...)...)
	cmd.Env = pythonEnv()
	return cmd, nil
}

func runPython(name string, args ...string) {
	cmd, err := pythonCmd(name, args...)
	if err != nil {
		fmt.Printf("[python] %s path error: %v\n", name, err)
		return
	}
	output, err := cmd.CombinedOutput()
	if err != nil {
		fmt.Printf("[python] %s failed: %v — %s\n", name, err, strings.TrimSpace(string(output)))
		return
	}
	if len(output) > 0 {
		fmt.Printf("[python] %s: %s\n", name, strings.TrimSpace(string(output)))
	}
}

// resolveNow re-verifies the Me chat unconditionally (post-pairing, post-history).
func resolveNow(logger waLog.Logger) {
	resolveMu.Lock()
	lastResolveAt = time.Now()
	resolveMu.Unlock()
	go func() {
		logger.Infof("Resolving Me chat (mechat.py --resolve --welcome)")
		runPython("mechat.py", "--resolve", "--welcome")
	}()
}

// scheduleResolve re-verifies the Me chat (reconnects, boot) — debounced so
// repeated triggers collapse into one run.
func scheduleResolve(logger waLog.Logger) {
	resolveMu.Lock()
	if time.Since(lastResolveAt) < 10*time.Second {
		resolveMu.Unlock()
		return
	}
	resolveMu.Unlock()
	resolveNow(logger)
}

// ── pairing ───────────────────────────────────────────────────────────────────

func startPairing(client *whatsmeow.Client, logger waLog.Logger) {
	qrChan, err := client.GetQRChannel(context.Background())
	if err != nil {
		logger.Errorf("Failed to get QR channel: %v", err)
		return
	}
	if err := client.Connect(); err != nil {
		logger.Errorf("Failed to connect for pairing: %v", err)
		return
	}
	for evt := range qrChan {
		switch evt.Event {
		case "code":
			if png, err := qrcode.Encode(evt.Code, qrcode.Medium, 256); err == nil {
				qrMu.Lock()
				currentQRDataURL = "data:image/png;base64," + base64.StdEncoding.EncodeToString(png)
				qrMu.Unlock()
			}
			fmt.Println("\nScan this QR code with your WhatsApp app (or open the setup page):")
			qrterminal.GenerateHalfBlock(evt.Code, qrterminal.L, os.Stdout)
		case "success":
			qrMu.Lock()
			currentQRDataURL = ""
			qrMu.Unlock()
			logger.Infof("Paired successfully")
			time.Sleep(2 * time.Second)
			resolveNow(logger)
			return
		}
	}
	logger.Warnf("QR channel closed without pairing")
}

// ── HTTP handlers ─────────────────────────────────────────────────────────────

func handleHealth(client *whatsmeow.Client, store *MessageStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		state := readMechatState()
		last := ""
		if state.JID != "" {
			last = store.LastMessageAt(state.JID)
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"ok":              client.IsConnected(),
			"connected":       client.IsConnected(),
			"mechat_resolved": state.JID != "",
			"last_message_at": last,
		})
	}
}

func handleSetupState(client *whatsmeow.Client, store *MessageStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		state := readMechatState()
		last := ""
		if state.JID != "" {
			last = store.LastMessageAt(state.JID)
		}
		qrMu.Lock()
		qrData := currentQRDataURL
		qrMu.Unlock()
		writeJSON(w, http.StatusOK, map[string]any{
			"connected":       client.IsConnected(),
			"paired":          client.Store.ID != nil,
			"qr_data_url":     qrData,
			"mechat_jid":      state.JID,
			"mechat_how":      state.How,
			"mechat_phone":    state.Phone,
			"welcomed":        state.Welcomed,
			"last_message_at": last,
			"gemini_key":      geminiKeyStatus(),
		})
	}
}

func handleReset(client *whatsmeow.Client, logger waLog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"ok": false})
			return
		}
		_ = os.Remove(storePath("mechat.json"))
		if err := client.Logout(context.Background()); err != nil {
			logger.Warnf("Logout during reset: %v", err)
		}
		go startPairing(client, logger)
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "message": "unlinked — pair again with a fresh QR"})
	}
}

// ── servers ───────────────────────────────────────────────────────────────────

func startServers(client *whatsmeow.Client, messageStore *MessageStore, logger waLog.Logger) {
	startInternalServer(client, messageStore)

	public := http.NewServeMux()
	public.HandleFunc("/", serveWizard)
	public.HandleFunc("/health", handleHealth(client, messageStore))
	public.HandleFunc("/setup/login", handleLogin)
	public.HandleFunc("/setup/state", withAuth(handleSetupState(client, messageStore)))
	public.HandleFunc("/setup/reset", withAuth(handleReset(client, logger)))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}
	go func() {
		fmt.Printf("Setup page on http://localhost:%s/ (health: /health)\n", port)
		if err := http.ListenAndServe(":"+port, public); err != nil {
			fmt.Printf("Setup server error: %v\n", err)
		}
	}()
}
