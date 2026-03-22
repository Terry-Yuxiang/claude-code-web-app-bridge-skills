# Safety Boundaries

## Never imply Claude Code ran when it did not

If the Claude bridge is unavailable, say so directly.
Do not present local reasoning as if it came from Claude Code.

## Use Claude as an assist layer, not an excuse to skip verification

Even when Claude returns a plausible fix:
- verify locally before claiming success
- preserve user constraints
- do not hide uncertainty

## Good delegation targets
- diagnosis
- patch plans
- alternative implementation comparisons
- structured debugging hypotheses
- code review style feedback

## Bad delegation targets
- destructive commands without user confirmation
- sensitive credential handling beyond necessity
- fabricated environment claims
- pretending Claude saw files it was never given

## Production note

If the user says this is production or production-adjacent:
- say so in the forwarded prompt
- prefer smallest safe fixes
- ask Claude for risk notes and verification steps
