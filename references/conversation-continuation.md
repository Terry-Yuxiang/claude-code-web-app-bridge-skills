# Conversation Continuation

## Storage layout

Conversations are stored **outside the skills folder** so they survive skills updates or deletion.

Default location: `~/.ai-bridge/claude-bridge/conversations/`
Override: set `claudeBridge.conversationsDir` in `config.json`, or set the `CLAUDE_BRIDGE_CONV_DIR` environment variable.

Each saved conversation lives in its own subdirectory:

```
~/.ai-bridge/claude-bridge/conversations/
  {slug}--{chatId}/
    meta.json            ← chat ID, title, URL, project, savedAt, totalTurns, tags
    conversation.jsonl   ← one JSON record per message, structured
    conversation.md      ← LLM-readable Markdown export
```

`meta.json` always contains the `chatId` and `url` fields needed to resume.

## When to save

- Save after **every completed assistant turn**, not only at end of session.
- Command:
  ```bash
  python scripts/claude_conversation_store.py --export-md
  ```
- Re-running is safe — only new turns are appended (deduplication by turn+role).

## How to resume a saved conversation

### Step 1 — find the chatId

```bash
cat conversations/<subdir>/meta.json
# look for "chatId" and "url"
```

### Step 2 — navigate the automation browser to that conversation

```bash
python scripts/claude_web_probe.py navigate --chat-id <chatId>
# or equivalently:
python scripts/claude_web_probe.py navigate --url https://claude.ai/chat/<chatId>
```

Wait ~2 seconds for the page to fully load.

### Step 3 — verify the page is on the right conversation

```bash
python scripts/claude_web_probe.py probe
# check "url" and "title" in the output
```

### Step 4 — send the next message

```bash
python scripts/claude_web_probe.py ask --question "Your follow-up message here"
```

### Step 5 — wait for the assistant to finish, then save

Poll with `read` until the response stabilises (no new text appearing), then:

```bash
python scripts/claude_conversation_store.py --export-md
```

## How to read a saved conversation as context

The `.md` file is structured for LLM consumption:

```
# Conversation title
| metadata table |

---
# Round 1
## Human
[user message]

## Assistant
[assistant reply]
### Artifact: <name>
```lang
<code>
```
### Search context
- Query: ...
  - [source title](url)

---
# Round 2
...
```

To load a prior conversation as context in a new Claude session, paste the relevant rounds from the `.md` file or reference the `.jsonl` for structured data.

## Caution

- The automation browser must be running with `--remote-debugging-port=9222`.
- You must be logged in to claude.ai in that browser.
- After navigating, always confirm the page URL matches before sending.
