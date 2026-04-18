# 🤖 wa-slash-commands

`wa-slash-commands` is a standalone, intelligent WhatsApp Slash Command CLI that acts as your personal Chief of Staff. It leverages the Gemini API to analyze your WhatsApp group chats and extract rich insights — tracking pending tasks, summarizing discussions, measuring team dynamics, and more.

## High-Level UX

This tool is designed to work in tandem with a local WhatsApp bridge (like the excellent [`whatsmeow`](https://github.com/tulir/whatsmeow) Go bridge). 

**Key Security Feature**: `wa-slash-commands` contains strict owner-protection logic. Even within a public or crowded group chat, the commands will **only execute** if they are sent by the bot owner's phone number. Other participants attempting to use `/sotu` or `/pending` will be silently ignored, maintaining privacy and controlling API usage.

## Available Commands

- `/sotu` — **State of the Union**: Synthesizes the last 30 days to identify the group purpose, big picture objectives, key themes, and decisions.
- `/pending` — **Critical Open Loops**: Scans the chat history to track ongoing initiatives, recent updates, and provides AI-synthesized "Next Steps" with identified owners.
- `/stats` — **Team Personas**: Analyzes participant activity, labels them with distinct collaboration styles (e.g., *The Driver*, *The Reviewer*, *The Lurker*), and identifies bottlenecks.
- `/recap` — **24h Timeline**: Extracts only the critical signals, decisions, and escalations from the past 24 hours (filtering out trivial chatter like "ok" and "done").
- `/eli5 <topic>` — **Explain Like I'm 5**: A context-aware search engine that explains a topic discussed in the chat to a professional standard.
- `/help` — Lists commands.

## Getting Started

### 1. Requirements

Ensure you are running an integration/bridge that stores messages in an SQLite database format (e.g., `messages.db` and `whatsapp.db`).
You will also need Python 3.10+.

### 2. Installation

Clone this repository and install the dependencies:

```bash
git clone https://github.com/yourusername/wa-slash-commands.git
cd wa-slash-commands
pip install -r requirements.txt
```

### 3. Configuration

`wa-slash-commands` relies strictly on environment variables. Copy the `.env.example` file to create your own configuration:

```bash
cp .env.example .env
```

Open `.env` and fill in your details:

- `GEMINI_API_KEY`: Your Google Gemini API Key.
- `OWNER_PHONE_NUMBER`: Your phone number (e.g., `919876543210`). The script will *only* respond to commands sent by this user.
- `MESSAGES_DB_PATH`: Path to your bridge's `messages.db`.
- `WHATSAPP_DB_PATH`: Path to your bridge's `whatsapp.db`.
- `WA_API_URL`: The webhook URL for your bridge to send the outbound response.

### 4. Running the CLI

Your bridge should be configured to execute `wacmd.py` when it intercepts a slash command:

```bash
python3 wacmd.py <chat_jid> <sender_jid> "<command_text>"
```

Example usage from your bridge hook:
```bash
python3 wacmd.py 123456789-98765@g.us 919876543210@s.whatsapp.net "/sotu"
```

## Anti-Hallucination & AI Reliability

When traversing large bodies of chat text, AI models can hallucinate or fail to return parsable structures. `wa-slash-commands` implements **Strict JSON Schema Enforcement**. We explicitly pass a rigid JSON structure directly to the Gemini API (`response_schema`). This guarantees that regardless of the chat's chaos, the output will always maintain its shape and be safely parsed by the formatting layer.
