# Validated Context for Better Claude Assistance

A live claude.ai test on this machine showed that for a failing Next.js build, Claude most wanted:
- exact error output / stack trace
- Next.js version
- Node version
- package manager and lockfile context
- relevant config files
- failing file / route / module if known
- recent changes before the failure started

## High-value context packet for coding/debugging

Include these first:
1. exact goal
2. exact failing command
3. exact error text
4. repo path
5. framework/runtime version
6. package manager
7. specific implicated file or module
8. recent change summary
9. constraints (production, minimal patch, no destructive changes)

## Lower-value context unless needed
- very large unrelated file dumps
- broad repo history
- long conversational background not tied to the failure
- vague summaries without exact error text

## Practical lesson
Claude is noticeably more useful when the prompt contains:
- a compact environment packet
- a specific task mode (diagnosis / patch-plan / review / compare-options)
- explicit constraints about production risk and patch size
- the actual task body pasted directly or uploaded as a file when the task is long
