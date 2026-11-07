#!/usr/bin/env python3
"""PostToolUse hook: auto-validate room YAML after Write|Edit.

Reads the hook payload from stdin. If the edited file is a room spec
(rooms/*.yaml or rooms/*.yml), runs the plugin's rules engine
(room_spatial.py <file> --check --json) and reports findings back:

- any ERROR findings  -> stdout {"decision": "block", "reason": "<findings>"}
  (PostToolUse "block" prompts Claude to address the problems)
- only WARN findings  -> stdout {"hookSpecificOutput": {"hookEventName":
  "PostToolUse", "additionalContext": "<findings>"}}
- no findings         -> no output

The hook must NEVER break editing: any failure (missing libs, bad stdin,
script error, non-JSON output, timeout) exits 0 silently. It must be safe
whether it executes on the host or in the Cowork VM.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_FINDINGS = 8
ROOM_RE = re.compile(r"(^|[/\\])rooms[/\\][^/\\]+\.ya?ml$")


def collect_findings(node, errors, warns):
    """Tolerantly extract 'SEVERITY RULE-ID: detail' findings from --json output."""
    if isinstance(node, str):
        text = node.strip()
        if text.startswith("ERROR"):
            errors.append(text)
        elif text.startswith(("WARN", "WARNING")):
            warns.append(text)
    elif isinstance(node, list):
        for item in node:
            collect_findings(item, errors, warns)
    elif isinstance(node, dict):
        severity = str(node.get("severity", "")).upper()
        message = node.get("message") or node.get("detail") or node.get("text")
        if severity in ("ERROR", "WARN", "WARNING") and message:
            rule = node.get("rule") or node.get("rule_id") or node.get("id") or ""
            line = "%s %s: %s" % (severity, rule, message) if rule else "%s: %s" % (severity, message)
            (errors if severity == "ERROR" else warns).append(line)
        else:
            for value in node.values():
                collect_findings(value, errors, warns)


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path or not ROOM_RE.search(file_path):
        return

    room_file = Path(file_path)
    if not room_file.is_absolute():
        room_file = Path(payload.get("cwd") or os.getcwd()) / room_file
    if not room_file.exists():
        return

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parent.parent)
    spatial = Path(plugin_root) / "scripts" / "room_spatial.py"
    if not spatial.exists():
        return

    result = subprocess.run(
        [sys.executable, str(spatial), str(room_file), "--check", "--json"],
        capture_output=True, text=True, timeout=30,
        cwd=str(room_file.parent.parent),
    )
    data = json.loads(result.stdout)  # non-JSON output -> ValueError -> silent exit

    errors, warns = [], []
    collect_findings(data, errors, warns)

    if errors:
        shown = errors[:MAX_FINDINGS]
        if len(errors) > MAX_FINDINGS:
            shown.append("(+%d more — run /planhaus:validate %s)" % (len(errors) - MAX_FINDINGS, room_file.stem))
        print(json.dumps({"decision": "block", "reason": "\n".join(shown)}))
    elif warns:
        shown = warns[:MAX_FINDINGS]
        if len(warns) > MAX_FINDINGS:
            shown.append("(+%d more — run /planhaus:validate %s)" % (len(warns) - MAX_FINDINGS, room_file.stem))
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "Spatial check warnings for %s:\n%s" % (room_file.name, "\n".join(shown)),
            }
        }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never break editing
    sys.exit(0)
