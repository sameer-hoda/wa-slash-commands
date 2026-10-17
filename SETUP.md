# 🚀 Setup Guide — wa-slash-commands

## Step 1 — Install dependencies

```bash
pip3 install -r requirements.txt
```

## Step 2 — Configure

```bash
cp .env.example .env
# edit .env: at minimum set GEMINI_API_KEY
```

Optional but recommended: set `SETUP_PASSWORD` so the setup page doesn't print a
new random password on every boot.

## Step 3 — Start the bridge

```bash
./start.sh          # builds bridge/wa-bridge on first run (needs Go 1.25+)
```

## Step 4 — Link WhatsApp from the setup page

Open **http://localhost:8081/** (or the port Railway provides):

1. Log in with your setup password (from `SETUP_PASSWORD`, or the one printed in the logs).
2. Scan the QR with WhatsApp → **Linked devices → Link a device**.
3. Wait a few seconds. The page shows:
   `Connected as +91… · Me chat: …` — this is where every command answer will land.
4. A one-time welcome message arrives in your Me chat. That's it.

If the page shows **Me chat: NOT FOUND YET**, the bot will not answer anything yet —
it has not identified your self-chat. Send any message to yourself
("Message yourself") once, then restart the bridge. Answers are never delivered to a
guessed chat.

---

## Running manually (after setup)

```bash
python3 wacmd.py <chat_jid> <sender_jid> "<command>"
```

Example:
```bash
python3 wacmd.py 12345678@g.us 919876543210@s.whatsapp.net "/help"
```

Note: manually-run commands send their answer to the resolved Me chat, exactly like
bridge-run commands. There is no mode that posts into the source chat.

---

## Me-chat resolution (what the bot is doing)

At launch and after every reconnect the bridge runs:

```bash
python3 mechat.py --resolve --welcome
```

which resolves the Me chat in this order:

1. Explicit `MECHAT_JID` (validated: owner, not a group)
2. Your own phone + LID from the pairing store (`whatsmeow_device`)
3. The freshest self-chat found in `messages.db` (PN or LID form); a brand-new
   account with no self-messages falls back to your own phone number — which is
   the self-chat by definition, not a guess

The result is persisted to `store/mechat.json` and shown on the setup page. If
resolution fails, nothing is sent anywhere and the reason is logged.

---

## Available Commands

Type these from your phone in **any** chat. The answer always arrives in your Me chat.

| Command | What it does |
|---|---|
| `/sotu` | 30-day state of the union |
| `/pending` | Open threads & next steps with owners |
| `/stats` | Team personas & activity share |
| `/recap` | 24h signal-only timeline |
| `/eli5 <topic>` | Explain anything using chat as context |
| `/help` | List all commands |

---

## Tests

```bash
python3 -m pytest tests/ -q     # offline, no network, no keys needed
```
