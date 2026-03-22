# Coding Modes

## 1. Diagnosis mode
Use when something is broken and you want Claude to identify likely root cause before editing code.

Ask Claude for:
- likely cause
- smallest safe fix
- verification steps
- risks

## 2. Patch-plan mode
Use when you want Claude to turn a coding task into a concrete step list.

Ask Claude for:
- exact files likely involved
- minimal change sequence
- what to verify after each step

## 3. Review mode
Use when you already have a patch or approach and want Claude to critique it.

Ask Claude for:
- weaknesses
- hidden risks
- missing tests
- edge cases

## 4. Compare-options mode
Use when there are multiple valid approaches.

Ask Claude for:
- option A / B / C
- tradeoffs
- recommended choice under current constraints

## Recommended default for long coding sessions
Start with:
1. diagnosis mode
2. patch-plan mode
3. local execution / verification
4. review mode if the fix is risky or messy
