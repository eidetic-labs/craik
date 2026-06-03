#!/usr/bin/env bash
# Smoke: does a PreToolUse hook returning "allow" override --permission-mode dontAsk's
# auto-deny baseline? This decides whether craik can gate via dontAsk (deny-by-default,
# hook = approval path that can ALLOW) or whether dontAsk only lets the hook DENY.
#
# Run this on a machine with the real `claude` CLI installed + authed. It uses an
# isolated, throwaway CLAUDE_CONFIG_DIR / project dir so it does NOT touch your real
# ~/.claude or repo. Read the PASS/FAIL interpretation at the bottom.
#
# Usage:  bash scripts/smoke_dontask_hook.sh
set -uo pipefail

command -v claude >/dev/null 2>&1 || { echo "FATAL: 'claude' CLI not found on PATH."; exit 1; }
echo "claude version: $(claude --version 2>/dev/null || echo unknown)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/proj/.claude"

# A PreToolUse hook that ALWAYS returns allow (Anthropic hook output shape).
cat > "$WORK/allow_hook.sh" <<'HOOK'
#!/usr/bin/env bash
cat >/dev/null   # drain the tool-request JSON on stdin
printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"smoke allow"}}'
exit 0
HOOK
chmod +x "$WORK/allow_hook.sh"

# A PreToolUse hook that ALWAYS denies (for the bypassPermissions control).
cat > "$WORK/deny_hook.sh" <<'HOOK'
#!/usr/bin/env bash
cat >/dev/null
printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"smoke deny"}}'
exit 2
HOOK
chmod +x "$WORK/deny_hook.sh"

write_settings () {  # $1 = hook script path
  cat > "$WORK/proj/.claude/settings.json" <<JSON
{ "hooks": { "PreToolUse": [ { "matcher": "*", "hooks": [ { "type": "command", "command": "$1" } ] } ] } }
JSON
}

MARKER="craik_smoke_marker_$$"
PROMPT="Use the Bash tool to run exactly: echo ${MARKER}"

run_case () {  # $1=label  $2=mode  $3=hook
  write_settings "$3"
  echo "================================================================"
  echo "CASE: $1   (--permission-mode $2, hook=$(basename "$3"))"
  echo "----------------------------------------------------------------"
  ( cd "$WORK/proj" && claude -p --permission-mode "$2" \
        --output-format text "$PROMPT" 2>&1 ) | tee "$WORK/out.txt"
  echo "----------------------------------------------------------------"
  if grep -q "$MARKER" "$WORK/out.txt"; then
    echo ">>> TOOL RAN (marker present): hook decision took effect → ALLOW honored."
  else
    echo ">>> TOOL DID NOT RUN (no marker): the call was blocked/denied."
  fi
}

# (1) THE CRUX: dontAsk + allow-hook. If the echo runs, a hook 'allow' overrides
#     dontAsk's auto-deny → craik CAN gate via dontAsk (approve-to-elevate works).
#     If it does NOT run, dontAsk only permits the hook to DENY, not approve →
#     we must gate via a different mode (e.g. auto).
run_case "CRUX: dontAsk + allow-hook" "dontAsk" "$WORK/allow_hook.sh"

# (2) CONTROL: bypassPermissions + deny-hook. Confirms a hook 'deny' still blocks
#     even in the escape-hatch mode (governance preserved).
run_case "CONTROL: bypass + deny-hook" "bypassPermissions" "$WORK/deny_hook.sh"

# (3) REFERENCE: auto + allow-hook (only meaningful if your account/CLI supports auto).
run_case "REFERENCE: auto + allow-hook" "auto" "$WORK/allow_hook.sh"

echo "================================================================"
echo "INTERPRETATION"
echo "  CASE 1 TOOL RAN     → gate via dontAsk (deny-by-default, hook approves). Best."
echo "  CASE 1 DID NOT RUN  → dontAsk can't be the gate; use the mode that DID run"
echo "                        in CASE 3 (auto), or report back and we decide."
echo "  CASE 2 must show DID NOT RUN (deny honored) — if it RAN, hook-deny is not"
echo "                        enforced in bypass on your version (important finding)."
