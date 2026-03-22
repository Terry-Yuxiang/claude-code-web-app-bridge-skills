#!/usr/bin/env python3
"""
Claude conversation store — API-based implementation.

Fetches the full structured conversation from Claude's REST API (via the
page's own authenticated fetch), capturing text, artifacts, and search
context in a clean JSONL format designed for LLM consumption.

Each saved record contains:
  turn        — 1-indexed round number (human+assistant = 1 turn)
  role        — "human" | "assistant"
  text        — concatenated text blocks (the actual prose)
  artifacts   — list of {title, artifact_type, code} for widgets/code/etc.
  search      — list of {query, sources:[{title,url}]} for web_search rounds
  timestamp   — ISO-8601 UTC
  source      — "api"
"""

import argparse
import asyncio
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Conversations directory — stored outside the skills folder so it survives
# skills updates or deletion.
#
# Resolution order:
#   1. CLAUDE_BRIDGE_CONV_DIR environment variable
#   2. claudeBridge.conversationsDir in config.json
#   3. Default: ~/.ai-bridge/claude-bridge/conversations/
# ---------------------------------------------------------------------------

def _resolve_conv_dir() -> Path:
    import os
    # 1. env var
    env = os.environ.get('CLAUDE_BRIDGE_CONV_DIR')
    if env:
        return Path(env).expanduser()
    # 2. config.json
    config_path = ROOT / 'config.json'
    if not config_path.exists():
        config_path = ROOT / 'config.example.json'
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding='utf-8'))
            custom = cfg.get('claudeBridge', {}).get('conversationsDir')
            if custom:
                return Path(custom).expanduser()
        except Exception:
            pass
    # 3. default
    return Path.home() / '.ai-bridge' / 'claude-bridge' / 'conversations'


CONV_DIR = _resolve_conv_dir()
CONV_DIR.mkdir(parents=True, exist_ok=True)


def conv_subdir(stem: str) -> Path:
    """Return (and create) the per-conversation subdirectory {CONV_DIR}/{stem}/."""
    d = CONV_DIR / stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_conversation(query: str):
    """
    Fuzzy-search saved conversations by name, abbreviation, or keywords.

    Matching strategy (highest score wins):
    1. chatId prefix match  → score 100
    2. Token overlap: each query word found anywhere in corpus  → +1 per token
    3. Prefix match: each query word is a prefix of any corpus word  → +1 per token
    4. Consecutive-initials match: short ALL-CAPS query (2-5 chars) matches
       the first letters of N consecutive title words  → +3
    5. Any-initials subsequence: letters of short ALL-CAPS token appear in
       order as first-letters of title words  → +2

    All comparisons are case-insensitive.
    Returns list sorted by score desc, then savedAt desc:
      [{'chatId', 'title', 'dir', 'savedAt', 'totalTurns', 'score'}, ...]
    """
    q = query.strip()
    tokens = [t.lower() for t in re.split(r'[^a-zA-Z0-9]+', q) if t]
    # ALL-CAPS short tokens (potential acronyms / ticker symbols)
    raw_tokens = re.split(r'[^a-zA-Z0-9]+', q)
    caps_tokens = [t.lower() for t in raw_tokens if t.isupper() and 2 <= len(t) <= 6]

    results = []
    for d in sorted(CONV_DIR.iterdir()):
        meta_file = d / 'meta.json'
        if not d.is_dir() or not meta_file.exists():
            continue
        try:
            m = json.loads(meta_file.read_text(encoding='utf-8'))
        except Exception:
            continue

        chat_id = m.get('chatId', '')
        title = m.get('title', '').replace(' - Claude', '').strip()
        tags = ' '.join(m.get('tags', []))
        corpus = (d.name + ' ' + title + ' ' + tags).lower()
        corpus_words = re.findall(r'[a-zA-Z0-9]+', corpus)
        title_words = re.findall(r'[a-zA-Z]+', title + ' ' + tags)
        title_initials = [w[0].lower() for w in title_words if w]

        # 1. chatId prefix
        if q.lower().replace('-', '') in chat_id.replace('-', ''):
            score = 100
        else:
            score = 0
            # 2. token overlap (substring of corpus)
            score += sum(1 for t in tokens if t in corpus)
            # 3. prefix match (each token is a prefix of any corpus word)
            score += sum(1 for t in tokens
                         if any(w.startswith(t) for w in corpus_words) and t not in corpus)
            # 4 & 5. acronym / initials matching for caps tokens
            for ct in caps_tokens:
                n = len(ct)
                # 4. consecutive initials: ct[0..n] matches title_initials[i..i+n]
                matched_consec = any(
                    title_initials[i:i+n] == list(ct)
                    for i in range(len(title_initials) - n + 1)
                )
                if matched_consec:
                    score += 3
                    continue
                # 5. subsequence of initials
                idx = 0
                for ch in ct:
                    while idx < len(title_initials) and title_initials[idx] != ch:
                        idx += 1
                    if idx < len(title_initials):
                        idx += 1
                    else:
                        break
                else:
                    score += 2  # full subsequence matched

        if score > 0:
            results.append({
                'chatId': chat_id,
                'title': title,
                'dir': str(d),
                'savedAt': m.get('savedAt', ''),
                'totalTurns': m.get('totalTurns', 0),
                'score': score,
            })

    results.sort(key=lambda x: (-x['score'], x['savedAt']))
    return results


# Tool names that produce user-visible artifacts (not utility calls)
ARTIFACT_TOOL_NAMES = re.compile(
    r'(visualize:show_widget|artifacts|repl|str_replace_based_edit_tool|computer)',
    re.IGNORECASE,
)
SEARCH_TOOL_NAMES = re.compile(r'web_search', re.IGNORECASE)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text.strip().lower()).strip('-')
    return text[:80] or 'claude-chat'


def get_claude_page():
    with urllib.request.urlopen('http://127.0.0.1:9222/json/list', timeout=5) as r:
        pages = json.loads(r.read().decode())
    claude_pages = [p for p in pages if p.get('type') == 'page' and 'claude.ai' in p.get('url', '')]
    if not claude_pages:
        raise SystemExit('Claude page not found on CDP port 9222')
    return claude_pages[-1]


async def cdp_eval(ws_url, expression, await_promise=True):
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        await ws.send(json.dumps({
            'id': 1,
            'method': 'Runtime.evaluate',
            'params': {'expression': expression, 'returnByValue': True, 'awaitPromise': await_promise}
        }))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get('id') == 1:
                result = msg.get('result', {}).get('result', {})
                if result.get('type') == 'string':
                    return result.get('value')
                return result.get('value')


# ---------------------------------------------------------------------------
# API fetch (runs inside the browser, uses the page's auth cookies)
# ---------------------------------------------------------------------------

JS_FETCH_CONVERSATION = '''
(async () => {
  const url = location.href;
  const chatId = (url.match(/chat\\/([a-f0-9-]+)/i) || [])[1];
  if (!chatId) return JSON.stringify({error: 'not on a chat page', url});

  // Discover the org-scoped API base from any prior resource request
  const entries = performance.getEntriesByType('resource');
  const apiEntry = entries.find(e => e.name.includes('/chat_conversations/'));
  if (!apiEntry) return JSON.stringify({error: 'no api entry in performance — try after a conversation is loaded'});

  const match = apiEntry.name.match(/(https:\\/\\/claude\\.ai\\/api\\/organizations\\/[^/]+)/);
  if (!match) return JSON.stringify({error: 'cannot extract org URL from: ' + apiEntry.name});
  const base = match[1];

  const apiUrl = base + '/chat_conversations/' + chatId +
    '?tree=True&rendering_mode=messages&render_all_tools=true';

  const resp = await fetch(apiUrl, {credentials: 'include'});
  if (!resp.ok) return JSON.stringify({error: 'API responded ' + resp.status, url: apiUrl});

  const data = await resp.json();
  return JSON.stringify(data);
})()
'''

JS_PAGE_META = r'''
(() => {
  const title = document.title || '';
  const url = location.href;
  const chatId = (url.match(/chat\/([a-f0-9-]+)/i) || [])[1] || 'unknown';
  return JSON.stringify({title, url, chatId});
})()
'''


# ---------------------------------------------------------------------------
# Content block parsing
# ---------------------------------------------------------------------------

def extract_message_record(msg, turn_number):
    """
    Convert one raw API chat_message into a clean record.

    Returns None if the message has no usable content.
    """
    role = msg.get('sender', 'unknown')   # 'human' | 'assistant'
    blocks = msg.get('content') or []

    text_parts = []
    artifacts = []
    search_rounds = []     # [{query, sources}]
    pending_search_query = None

    for block in blocks:
        btype = block.get('type', '')

        if btype == 'text':
            t = (block.get('text') or '').strip()
            # Drop suggestion-overlay echoes like "Q: What should Round 2 focus on? A: [No preference]"
            if role == 'human' and re.match(r'^Q:', t):
                continue
            if t:
                text_parts.append(t)

        elif btype == 'thinking':
            pass  # internal reasoning — intentionally omitted

        elif btype == 'tool_use':
            name = block.get('name', '')
            inp = block.get('input') or {}

            if SEARCH_TOOL_NAMES.search(name):
                pending_search_query = inp.get('query', '')

            elif ARTIFACT_TOOL_NAMES.search(name):
                artifact_code = (
                    inp.get('widget_code')
                    or inp.get('code')
                    or inp.get('content')
                    or inp.get('command')
                    or ''
                )
                artifacts.append({
                    'title': inp.get('title') or inp.get('name') or name,
                    'artifact_type': name,
                    'code': artifact_code,
                })

        elif btype == 'tool_result':
            content_list = block.get('content') or []
            if pending_search_query is not None:
                sources = []
                for item in content_list:
                    if item.get('type') == 'knowledge':
                        title = item.get('title', '')
                        url = item.get('url', '')
                        if title or url:
                            sources.append({'title': title, 'url': url})
                search_rounds.append({
                    'query': pending_search_query,
                    'sources': sources[:5],   # keep top 5 per query
                })
                pending_search_query = None

    text = '\n\n'.join(text_parts).strip()

    # Skip messages that are truly empty (e.g. interrupted / placeholder)
    if not text and not artifacts:
        return None

    record = {
        'turn': turn_number,
        'role': role,
        'text': text,
        'timestamp': now_iso(),
        'source': 'api',
    }
    if artifacts:
        record['artifacts'] = artifacts
    if search_rounds:
        record['search'] = search_rounds

    return record


def assign_turns(raw_messages):
    """
    Pair human+assistant messages into numbered turns.
    Turn N = the Nth human message and its following assistant reply.
    """
    records = []
    turn = 0
    for msg in raw_messages:
        role = msg.get('sender', '')
        if role == 'human':
            turn += 1
        rec = extract_message_record(msg, turn)
        if rec:
            records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_existing_ids(path: Path):
    """Return set of (turn, role) already saved."""
    seen = set()
    if not path.exists():
        return seen
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            obj = json.loads(line)
            if 'turn' in obj and 'role' in obj:
                seen.add((obj['turn'], obj['role']))
        except Exception:
            continue
    return seen


def append_jsonl(path: Path, rows):
    with path.open('a', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _detect_lang(artifact_type: str, code: str) -> str:
    """Guess a fenced-code-block language tag from artifact type and code content."""
    t = artifact_type.lower()
    if 'react' in t:
        return 'jsx'
    if 'python' in t or 'repl' in t:
        return 'python'
    if 'svg' in code[:60]:
        return 'svg'
    if re.search(r'<canvas|Chart\(|new Chart', code[:300]):
        return 'html'
    if code.lstrip().startswith('<'):
        return 'html'
    if 'function ' in code or 'const ' in code or 'let ' in code:
        return 'js'
    return 'html'


def export_to_md(jsonl_path: Path, meta_path: Path) -> Path:
    """
    Convert a saved JSONL conversation to a Markdown file optimised for LLM reading.

    Structure:
      # <title>
      metadata block
      ---
      # Round N
      ## Human
      prose text
      ### Artifact: <title>  (if any)
      ```<lang>
      code
      ```
      ## Assistant
      prose text
      ### Artifact: <title>  (if any)
      ### Search context  (if any)
      - query / sources
    """
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    records = [json.loads(l) for l in jsonl_path.read_text(encoding='utf-8').splitlines() if l.strip()]

    lines = []

    # ── header ──────────────────────────────────────────────────────────────
    title = meta.get('title', '').replace(' - Claude', '').strip()
    lines.append(f'# {title}')
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('|---|---|')
    lines.append(f'| Chat ID | `{meta.get("chatId","")}` |')
    lines.append(f'| URL | {meta.get("url","")} |')
    lines.append(f'| Project | {meta.get("project","")} |')
    lines.append(f'| Turns | {meta.get("totalTurns","")} |')
    lines.append(f'| Saved | {meta.get("savedAt","")} |')
    lines.append('')

    # ── group by turn, emit Round headings ──────────────────────────────────
    # Collect records per turn number
    from collections import defaultdict
    turns: dict = defaultdict(dict)
    for rec in records:
        t = rec.get('turn', 0)
        role = rec.get('role', 'unknown')
        turns[t][role] = rec

    for turn_num in sorted(turns.keys()):
        lines.append('---')
        lines.append(f'# Round {turn_num}')
        lines.append('')

        for role_key, heading in [('human', 'Human'), ('assistant', 'Assistant')]:
            rec = turns[turn_num].get(role_key)
            if not rec:
                continue

            lines.append(f'## {heading}')
            lines.append('')

            # prose
            text = rec.get('text', '').strip()
            if text:
                lines.append(text)
                lines.append('')

            # artifacts
            for a in rec.get('artifacts', []):
                lines.append(f'### Artifact: {a["title"]}')
                lines.append(f'*type: `{a["artifact_type"]}`*')
                lines.append('')
                lang = _detect_lang(a['artifact_type'], a['code'])
                lines.append(f'```{lang}')
                lines.append(a['code'].strip())
                lines.append('```')
                lines.append('')

            # search context
            search = rec.get('search', [])
            if search:
                lines.append('### Search context')
                for s in search:
                    lines.append(f'- **Query**: {s["query"]}')
                    for src in s.get('sources', []):
                        url = src.get('url', '')
                        ttl = src.get('title', url)
                        if url:
                            lines.append(f'  - [{ttl}]({url})')
                        elif ttl:
                            lines.append(f'  - {ttl}')
                lines.append('')

    md_path = jsonl_path.with_suffix('.md')
    md_path.write_text('\n'.join(lines), encoding='utf-8')
    return md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def cmd_find(query: str):
    """Print fuzzy-matched conversations as JSON and exit."""
    results = find_conversation(query)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_list():
    """Print all saved conversations as JSON and exit."""
    rows = []
    for d in sorted(CONV_DIR.iterdir()):
        meta_file = d / 'meta.json'
        if not d.is_dir() or not meta_file.exists():
            continue
        try:
            m = json.loads(meta_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        rows.append({
            'chatId': m.get('chatId', ''),
            'title': m.get('title', '').replace(' - Claude', '').strip(),
            'tags': m.get('tags', []),
            'dir': str(d),
            'savedAt': m.get('savedAt', '')[:10],
            'totalTurns': m.get('totalTurns', 0),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_tag(chat_id_prefix: str, tags: list):
    """Add tags to a saved conversation's meta.json."""
    results = find_conversation(chat_id_prefix)
    if not results:
        raise SystemExit(f'No conversation found matching: {chat_id_prefix}')
    target = results[0]
    meta_path = Path(target['dir']) / 'meta.json'
    m = json.loads(meta_path.read_text(encoding='utf-8'))
    existing = set(m.get('tags', []))
    existing.update(tags)
    m['tags'] = sorted(existing)
    meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'chatId': m['chatId'], 'tags': m['tags']}, indent=2))


async def main():
    ap = argparse.ArgumentParser(description='Persist current Claude chat to JSONL + metadata (API-based)')
    ap.add_argument('--project', default='general')
    ap.add_argument('--export-md', action='store_true', help='also write a Markdown file alongside the JSONL')
    ap.add_argument('--find', metavar='QUERY', help='fuzzy-search saved conversations and exit')
    ap.add_argument('--list', action='store_true', help='list all saved conversations and exit')
    ap.add_argument('--tag', nargs='+', metavar='TAG',
                    help='add tags to a conversation: --tag <chatId-prefix> <tag1> [tag2 ...]')
    args = ap.parse_args()

    if args.find:
        cmd_find(args.find)
        return
    if args.list:
        cmd_list()
        return
    if args.tag:
        if len(args.tag) < 2:
            ap.error('--tag requires a chatId prefix followed by at least one tag')
        cmd_tag(args.tag[0], args.tag[1:])
        return

    page = get_claude_page()
    ws_url = page['webSocketDebuggerUrl']

    # Get page meta (title, url, chatId)
    meta_raw = await cdp_eval(ws_url, JS_PAGE_META, await_promise=False)
    if not meta_raw:
        raise SystemExit('Could not read page meta')
    meta_info = json.loads(meta_raw)
    title = meta_info['title']
    url = meta_info['url']
    chat_id = meta_info['chatId']

    # Fetch full conversation from API
    api_raw = await cdp_eval(ws_url, JS_FETCH_CONVERSATION, await_promise=True)
    if not api_raw:
        raise SystemExit('API fetch returned no data')
    api_data = json.loads(api_raw)
    if 'error' in api_data:
        raise SystemExit(f"API error: {api_data['error']}")

    raw_messages = api_data.get('chat_messages') or []
    records = assign_turns(raw_messages)

    # File paths — each conversation lives in its own subdirectory
    slug = slugify(title.replace(' - Claude', '').strip())
    stem = f"{slug}--{chat_id}"
    conv_dir = conv_subdir(stem)
    meta_path = conv_dir / 'meta.json'
    jsonl_path = conv_dir / 'conversation.jsonl'

    # Save meta
    meta_path.write_text(json.dumps({
        'chatId': chat_id,
        'title': title,
        'url': url,
        'project': args.project,
        'savedAt': now_iso(),
        'source': 'api',
        'totalTurns': max((r['turn'] for r in records), default=0),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    # Always overwrite with clean API data (drop any stale dom-structured records)
    if jsonl_path.exists():
        existing = [json.loads(l) for l in jsonl_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        stale = any(r.get('source') != 'api' for r in existing)
        if stale:
            jsonl_path.unlink()

    seen = load_existing_ids(jsonl_path)
    new_rows = [r for r in records if (r['turn'], r['role']) not in seen]
    append_jsonl(jsonl_path, new_rows)

    result = {
        'ok': True,
        'dir': str(conv_dir),
        'meta': str(meta_path),
        'jsonl': str(jsonl_path),
        'totalMessages': len(records),
        'newMessagesWritten': len(new_rows),
    }
    if args.export_md:
        md_path = export_to_md(jsonl_path, meta_path)
        result['md'] = str(md_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
