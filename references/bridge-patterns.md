# Claude Code Bridge Patterns

## Goal

Let the assistant forward selected tasks to Claude Code with enough context to be useful, but not so much context that it wastes tokens.

## Current runtime reality

On this machine at the time of creation:
- a real **claude.ai web bridge** was validated successfully through the dedicated browser and CDP
- an ACP attempt to call **Claude Code** failed because the ACP backend was not configured

That means the bridge concept is valid and partially proven live, but Claude Code runtime execution is still dependency-gated.
Keep this fact explicit in any user-facing use until a real Claude Code runtime is connected.

## Minimal context packet for a failing web-app build

Include these fields when available:
- OS / machine
- repo path
- app/framework (for example Next.js)
- runtime versions (Node / package manager)
- exact command that failed
- exact error output
- what changed recently
- what kind of answer is wanted

## Example forwarding prompt

```text
You are Claude Code helping with a production-adjacent web app issue.

Environment:
- OS: macOS
- Repo: /path/to/repo
- App: Next.js site
- Node: v22.x
- Browser automation: Chrome/CDP involved

Task:
Debug a failing build and propose the smallest safe fix.

Failing command:
npm run build

Observed error:
<paste exact error>

Constraints:
- keep changes minimal
- do not assume access to hidden services
- prefer a stepwise diagnosis

Please provide:
1. likely root cause
2. minimal fix
3. verification steps
4. any risks
```

## Output modes Claude can be asked for

### 1. Diagnosis mode
Use when you want root-cause analysis before touching code.

### 2. Patch-plan mode
Use when you want a precise small-step implementation plan.

### 3. Diff-review mode
Use when you already have a patch and want second-opinion review.

### 4. Compare-options mode
Use when multiple implementation strategies exist.

## Design guidance

Keep forwarded prompts compact.
Do not dump entire repositories into the bridge by default.
Prefer:
- exact error
- exact file path
- exact command
- 3 to 7 lines of surrounding context

Only escalate to larger context when the first Claude pass is insufficient.

## Important prompt-delivery lesson

For browser-based Claude bridging, do **not** assume Claude can read a local file path just because the file exists on disk.
Reliable ways to deliver task content are:
1. paste the relevant task content directly into Claude
2. upload the relevant file to Claude

Unreliable pattern:
- "read local file X in my project" when Claude was never actually given the file contents

For large coding tasks, prefer:
- short bridge instruction in the prompt
- then pasted task body or uploaded task file
- then follow-up mode request (diagnosis / patch-plan / review / compare-options)

## Conversation persistence pattern

To reduce context loss and enable multi-turn continuation:
- save each Claude chat into `~/.ai-bridge/claude-bridge/conversations/`
- use `jsonl + meta` files
- name files with chat title slug plus Claude chat id
- write user/assistant turns in a format that is easy for another AI to read later
- prefer structured records over raw text dumps when possible
