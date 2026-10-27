package main

// setup_web.go — launch layer for the slash-commands MVP:
//   * STORE_DIR-aware paths + bridge token for the internal API
//   * web setup page: QR (PNG data-URL, auto-refresh), Gemini-key tick,
//     connected view, Unlink — behind a setup password
//   * /health for liveness checks (Supervisor + clean-room probes)
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
	// geminiKeyLive holds a just-validated key in memory only. It is the
	// bridge's only key store besides the Supervisor-provided env var.
	geminiKeyLive string

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

// Local Mac mode: the setup page is loopback-only (see setupBindAddr), so
// the legacy cloud password gate is skipped via SETUP_NO_AUTH=1, which the
// bundled app always sets. Without this, first launch prints a generated
// password nowhere the user can find it.
func noAuthMode() bool {
	return os.Getenv("SETUP_NO_AUTH") == "1"
}

func setupBindAddr(port string) string {
	return "127.0.0.1:" + port
}

func validCookie(r *http.Request) bool {
	if noAuthMode() {
		return true
	}
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

func classifyGeminiOutput(out string) string {
	switch out {
	case "valid", "invalid", "missing":
		return out
	default:
		return "invalid"
	}
}

// The Gemini key is Keychain-only: it arrives from the Supervisor as the
// GEMINI_API_KEY process env var, or is validated live in handleGeminiKey
// and kept in process memory. It is NEVER written to disk — there is no
// gemini_key file and no file fallback anywhere in this bridge.
func noteValidatedKey(key string) {
	geminiMu.Lock()
	geminiKeyLive = strings.TrimSpace(key)
	geminiMu.Unlock()
}

// resolveGeminiKey precedence: explicit key > validated in-memory key >
// Supervisor-provided process env. Disk is not consulted, by design.
func resolveGeminiKey(key string) string {
	if strings.TrimSpace(key) != "" {
		return strings.TrimSpace(key)
	}
	geminiMu.Lock()
	live := geminiKeyLive
	geminiMu.Unlock()
	if live != "" {
		return live
	}
	return strings.TrimSpace(os.Getenv("GEMINI_API_KEY"))
}

// checkGeminiKey shells gemini_check.py, optionally with an explicit key.
// Clean stdout wins over the exit code (0 valid / 1 missing / 2 invalid).
func checkGeminiKey(key string) string {
	cmd, err := pythonCmd("gemini_check.py")
	if err != nil {
		return "invalid"
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	run := exec.CommandContext(ctx, cmd.Path, cmd.Args[1:]...)
	env := cmd.Env
	if resolved := resolveGeminiKey(key); resolved != "" {
		env = append(append([]string{}, env...),
			"GEMINI_API_KEY="+resolved)
	}
	run.Env = env
	out, _ := run.Output()
	return classifyGeminiOutput(strings.TrimSpace(string(out)))
}

func geminiKeyStatus() string {
	geminiMu.Lock()
	if time.Since(geminiCheckedAt) < time.Minute && geminiKeyCached != "" {
		cached := geminiKeyCached
		geminiMu.Unlock()
		return cached
	}
	live := geminiKeyLive
	geminiMu.Unlock()
	// checkGeminiKey resolves (and locks) on its own — never hold geminiMu
	// across it. Go mutexes are not reentrant; holding it here deadlocks
	// every /setup/state poll.
	status := checkGeminiKey(live)
	geminiMu.Lock()
	geminiKeyCached = status
	geminiCheckedAt = time.Now()
	geminiMu.Unlock()
	return status
}

func resetGeminiCache() {
	geminiMu.Lock()
	geminiKeyCached = ""
	geminiMu.Unlock()
}

// handleGeminiKey tests a pasted key live and keeps it in process memory
// when valid, so the setup page itself completes the key step — no terminal,
// no restart, and nothing on disk. The Swift shell persists the key to the
// Keychain itself and passes it back as GEMINI_API_KEY on the next launch.
func handleGeminiKey(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"ok": false})
		return
	}
	var body struct {
		Key string `json:"key"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "status": "missing"})
		return
	}
	status := checkGeminiKey(body.Key)
	if status == "valid" {
		noteValidatedKey(body.Key)
		resetGeminiCache()
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": status == "valid", "status": status})
}

// ── python bridge helpers ─────────────────────────────────────────────────────

func pythonEnv() []string {
	// os.Environ already carries the Supervisor-provided GEMINI_API_KEY.
	// A just-validated live key covers the window before the Supervisor
	// relaunches with the Keychain key. Disk is never consulted.
	env := append(os.Environ(),
		"BRIDGE_TOKEN="+bridgeTokenVal,
		"STORE_DIR="+absStorePath(""),
		"MESSAGES_DB_PATH="+absStorePath("messages.db"),
		"WHATSAPP_DB_PATH="+absStorePath("whatsapp.db"),
		"WA_API_URL=http://127.0.0.1:8090/api/send",
	)
	if os.Getenv("GEMINI_API_KEY") == "" {
		geminiMu.Lock()
		live := geminiKeyLive
		geminiMu.Unlock()
		if live != "" {
			env = append(env, "GEMINI_API_KEY="+live)
		}
	}
	return env
}

// scriptSearchDirs orders Python lookup: the bundled app sets
// PY_SCRIPTS_DIR (Resources/python); dev checkouts fall back to CWD,
// scripts/, parent, parent scripts/.
func scriptSearchDirs() []string {
	dirs := []string{}
	if d := os.Getenv("PY_SCRIPTS_DIR"); d != "" {
		dirs = append(dirs, d)
	}
	return append(dirs, ".", "scripts", "..", filepath.Join("..", "scripts"))
}

func findScript(name string) string {
	for _, dir := range scriptSearchDirs() {
		cand := filepath.Join(dir, name)
		if _, err := os.Stat(cand); err == nil {
			return cand
		}
	}
	return name
}

// pythonCandidates orders interpreters: explicit override first, then the
// common Homebrew locations (which carry user-installed deps), then bare
// PATH lookup. GUI-launched apps get a minimal PATH where "python3" is the
// system interpreter without our deps — never rely on it alone.
// bundlePythonFrom maps a Contents/MacOS binary to its bundled interpreter.
func bundlePythonFrom(exe string) string {
	if filepath.Base(filepath.Dir(exe)) != "MacOS" {
		return ""
	}
	p := filepath.Join(filepath.Dir(filepath.Dir(exe)), "Resources",
		"python-runtime", "bin", "python3")
	if st, err := os.Stat(p); err == nil && !st.IsDir() {
		return p
	}
	return ""
}

// bundlePython locates the interpreter shipped inside Mosaic.app.
func bundlePython() string {
	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	return bundlePythonFrom(exe)
}

func pythonCandidates() []string {
	c := []string{}
	if p := strings.TrimSpace(os.Getenv("MOSAIC_PYTHON")); p != "" {
		c = append(c, p)
	}
	if p := bundlePython(); p != "" {
		c = append(c, p)
	}
	return append(c, "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "python3")
}

var cachedPython = ""

func findPython() string {
	if cachedPython != "" {
		return cachedPython
	}
	for _, cand := range pythonCandidates() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		cmd := exec.CommandContext(ctx, cand, "-c",
			"import google.generativeai,dotenv,requests")
		err := cmd.Run()
		cancel()
		if err == nil {
			cachedPython = cand
			return cand
		}
	}
	return "python3"
}

func pythonCmd(name string, args ...string) (*exec.Cmd, error) {
	script := findScript(name)
	abs, err := filepath.Abs(script)
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(findPython(), append([]string{abs}, args...)...)
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
	public.HandleFunc("/setup/gemini", withAuth(handleGeminiKey))
	public.HandleFunc("/setup/reset", withAuth(handleReset(client, logger)))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}
	go func() {
		fmt.Printf("Setup page on http://localhost:%s/ (health: /health)\n", port)
		// Fail fast: a bridge that cannot bind is deaf but looks alive.
		// The supervisor owns restart policy (backoff + crash-loop guard).
		if err := http.ListenAndServe(setupBindAddr(port), public); err != nil {
			fmt.Printf("Setup server error: %v\n", err)
			os.Exit(1)
		}
	}()
}
