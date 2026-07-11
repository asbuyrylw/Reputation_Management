#!/bin/bash
# vexp-guard: deny Grep/Glob when a HEALTHY vexp daemon is running for THIS
# workspace, so the agent uses run_pipeline/get_skeleton instead (token savings).
# Fails OPEN (allow) whenever vexp is not clearly running.
# Cross-platform: Unix socket (daemon.sock) OR Windows named-pipe marker
# (daemon.pipe); liveness via `kill -0` (Unix) OR `tasklist` (Windows/Git Bash).
VEXP_DIR="${CLAUDE_PROJECT_DIR:-.}/.vexp"
allow(){ printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"vexp not running here; direct search allowed."}}'; exit 0; }
deny(){  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"vexp daemon is running for this repo - use run_pipeline (or get_skeleton) instead of Grep/Glob to save tokens."}}'; exit 0; }

[ -f "$VEXP_DIR/healthy" ]      || allow
[ -f "$VEXP_DIR/daemon.pid" ]  || allow
{ [ -S "$VEXP_DIR/daemon.sock" ] || [ -e "$VEXP_DIR/daemon.pipe" ]; } || allow
PID="$(tr -dc '0-9' < "$VEXP_DIR/daemon.pid" 2>/dev/null)"
[ -n "$PID" ] || allow

kill -0 "$PID" 2>/dev/null && deny
command -v tasklist >/dev/null 2>&1 && tasklist //FI "PID eq $PID" //NH 2>/dev/null | grep -qw "$PID" && deny
allow
