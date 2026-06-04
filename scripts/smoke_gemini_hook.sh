#!/usr/bin/env bash
# Smoke: which `gemini --approval-mode` makes a BeforeTool hook the AUTHORITATIVE
# headless gate? This is the Gemini counterpart of scripts/smoke_dontask_hook.sh.
#
# Unlike claude (whose `dontAsk` gate was confirmed by an operator smoke), Gemini's
# gate mode is NOT yet verified. craik already wires the mode-INDEPENDENT mechanisms
# (the BeforeTool craik-hook is registered into .gemini/settings.json + the workspace
# is trusted). This smoke settles the OPEN question: under which `--approval-mode`
# does a BeforeTool hook returning "allow" actually let the tool run (hook honored),
# and is a hook "deny" enforced? Gemini's approval modes are {default, auto_edit,
# yolo, plan}; there is NO `dontAsk`-equivalent.
#
# Run on a machine with the real `gemini` CLI installed + authed. It uses an
# isolated, throwaway project dir + HOME so it does NOT touch your real ~/.gemini or
# repo. The BeforeTool hook ONLY fires with the workspace TRUSTED
# (GEMINI_CLI_TRUST_WORKSPACE=true is load-bearing -- it silently no-fires otherwise).
#
# IMPORTANT (read the RAW OUTPUT, not just the verdict): the marker-grep can
# FALSE-POSITIVE when the model echoes the command back in its prose (the claude
# smoke had exactly this bug). This script PRINTS the raw model output for every
# case and asks YOU to read it -- the auto-verdict is a hint, not the answer.
#
# Usage:  bash scripts/smoke_gemini_hook.sh
set -uo pipefail

command -v gemini >/dev/null 2>&1 || { echo "FATAL: 'gemini' CLI not found on PATH."; exit 1; }
echo "gemini version: $(gemini --version 2>/dev/null || echo unknown)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/proj/.gemini"

# A BeforeTool hook that ALWAYS returns allow (Gemini hook output shape).
cat > "$WORK/allow_hook.sh" <<'HOOK'
#!/usr/bin/env bash
cat >/dev/null   # drain the tool-request JSON on stdin
printf '%s' '{"decision":"allow","reason":"smoke allow"}'
exit 0
HOOK
chmod +x "$WORK/allow_hook.sh"

# A BeforeTool hook that ALWAYS denies. Gemini's hook-deny dialect is exit code 2
# (google-cli.md §3.4); the JSON decision is emitted too for robustness.
cat > "$WORK/deny_hook.sh" <<'HOOK'
#!/usr/bin/env bash
cat >/dev/null
printf '%s' '{"decision":"deny","reason":"smoke deny"}'
exit 2
HOOK
chmod +x "$WORK/deny_hook.sh"

write_settings () {  # $1 = hook script path
  cat > "$WORK/proj/.gemini/settings.json" <<JSON
{ "hooks": { "BeforeTool": [ { "matcher": "*", "hooks": [ { "type": "command", "command": "$1" } ] } ] } }
JSON
}

MARKER="craik_smoke_marker_$$"
PROMPT="Use the shell tool to run exactly: echo ${MARKER}"

run_case () {  # $1=label  $2=mode  $3=hook
  write_settings "$3"
  echo "================================================================"
  echo "CASE: $1   (--approval-mode $2, hook=$(basename "$3"))"
  echo "----------------------------------------------------------------"
  # GEMINI_CLI_TRUST_WORKSPACE=true is load-bearing: the BeforeTool hook silently
  # does NOT fire in an untrusted workspace. HOME is isolated so we never read the
  # operator's real ~/.gemini.
  ( cd "$WORK/proj" && HOME="$WORK/home" GEMINI_CLI_TRUST_WORKSPACE=true \
        gemini -p "$PROMPT" --approval-mode "$2" 2>&1 ) | tee "$WORK/out.txt"
  echo "----------------------------------------------------------------"
  echo ">>> RAW OUTPUT ABOVE -- READ IT. The verdict below greps for the marker,"
  echo "    which FALSE-POSITIVES if the model merely echoed the command in prose."
  if grep -q "$MARKER" "$WORK/out.txt"; then
    echo ">>> AUTO-VERDICT: marker present -> tool LIKELY RAN (hook ALLOW honored?)."
    echo "    CONFIRM in the raw output that the echo actually EXECUTED, not echoed."
  else
    echo ">>> AUTO-VERDICT: no marker -> tool LIKELY did NOT run (blocked/denied)."
  fi
}

# Sweep the candidate approval modes with the ALLOW hook: we want the mode where a
# BeforeTool 'allow' makes the tool run (hook = authoritative approval path).
run_case "ALLOW-hook under default"   "default"   "$WORK/allow_hook.sh"
run_case "ALLOW-hook under auto_edit" "auto_edit" "$WORK/allow_hook.sh"
run_case "ALLOW-hook under yolo"      "yolo"      "$WORK/allow_hook.sh"

# DENY control under each candidate: a BeforeTool 'deny' MUST block the tool
# (governance preserved). yolo is the riskiest -- if deny is NOT enforced under
# yolo, yolo cannot be the craik gate (important finding).
run_case "DENY-hook under default"    "default"   "$WORK/deny_hook.sh"
run_case "DENY-hook under auto_edit"  "auto_edit" "$WORK/deny_hook.sh"
run_case "DENY-hook under yolo"       "yolo"      "$WORK/deny_hook.sh"

echo "================================================================"
echo "INTERPRETATION (read the RAW OUTPUT for each case first)"
echo "  Pick the --approval-mode where BOTH hold headlessly:"
echo "    * ALLOW-hook case: the echo ACTUALLY RAN  -> hook 'allow' is honored."
echo "    * DENY-hook case:  the echo did NOT run    -> hook 'deny' is enforced."
echo "  That mode is the AUTHORITATIVE craik gate for gemini. Wire it into"
echo "  GoogleCLI.run() (the gemini analogue of claude's dontAsk) once confirmed."
echo "  Until then craik does NOT force a gemini gate mode -- it registers the hook"
echo "  + trusts the workspace and passes the operator's --approval-mode through."
echo "  If NO single mode satisfies both, report the full matrix back."
