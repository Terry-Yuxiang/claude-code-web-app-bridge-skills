# Installation

## Required local environment

- macOS
- Google Chrome
- A dedicated automation browser/profile that can be reused for Claude and browser-driven workflows
- Python 3
- Chrome DevTools Protocol access on port `9222`

## Python dependencies

Create a local virtual environment inside the skill/project directory and install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

Current required packages:
- `websockets`
- `requests`

## Runtime expectation

This skill can operate in two different bridge modes:

1. **Claude web bridge via claude.ai**
   - Already validated on this machine
   - Uses browser automation and CDP

2. **Claude Code / ACP bridge**
   - Depends on ACP backend or another callable Claude Code runtime
   - If unavailable, the skill must say so honestly

## Minimum verification steps

### 1. Basic probe, ask, read

```bash
. .venv/bin/activate
python scripts/claude_web_probe.py probe
python scripts/claude_web_probe.py ask --question "Reply with exactly: CLAUDE_BRIDGE_OK"
sleep 8
python scripts/claude_web_probe.py read
```

Expected: `read` output contains `CLAUDE_BRIDGE_OK` in the tail text.

### 2. Save conversation to subdirectory

```bash
python scripts/claude_conversation_store.py --export-md --project bridge-testing
```

Expected output:
```json
{
  "ok": true,
  "dir": "conversations/<slug>--<chatId>/",
  "meta": "...meta.json",
  "jsonl": "...conversation.jsonl",
  "totalMessages": ...,
  "newMessagesWritten": ...,
  "md": "...conversation.md"
}
```

Verify the subdirectory was created:
```bash
ls ~/.ai-bridge/claude-bridge/conversations/<slug>--<chatId>/
# should show: conversation.jsonl  meta.json  conversation.md
```

### 3. Navigate to a saved conversation and continue it

```bash
# Get the URL of a previously saved conversation
cat conversations/<slug>--<chatId>/meta.json

# Navigate using chat ID
python scripts/claude_web_probe.py navigate --chat-id <chatId>

# Or navigate using full URL
python scripts/claude_web_probe.py navigate --url https://claude.ai/chat/<chatId>
```

Expected:
```json
{"ok": true, "navigatedTo": "https://claude.ai/chat/<chatId>"}
```

Verify the browser landed on the right page:
```bash
sleep 2
python scripts/claude_web_probe.py probe
# check "title" and "url" match the saved conversation
```

Send a follow-up message:
```bash
python scripts/claude_web_probe.py ask --question "Your follow-up message"
sleep 15
python scripts/claude_web_probe.py read
```

Save the new turn:
```bash
python scripts/claude_conversation_store.py --export-md
# newMessagesWritten should be 2 (new human + assistant turn)
```

Only claim the bridge is working if each step above produces the expected output.
