---
name: planhaus-validate
description: Validate room geometry and run the clearance rules engine — trace closure, area match, collisions, plus rule findings with IDs
argument-hint: "<room-name>"
when_to_use: After any room YAML change, before placing or selecting furniture, or when the user asks whether a layout is correct or feasible.
allowed-tools: Bash(python3:*)
---

# Validate Room

Check that a room's geometry is correct AND that the layout passes the clearance rules.

## Steps

1. Find and read the room YAML file (`rooms/<room-name>.yaml`).

2. Run the spatial tool with the rules engine:
   ```bash
   python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --check
   ```
   Add `--json` when you need machine-readable output (positions, warnings, rule results) for programmatic processing.

3. Report **geometry** first — PASS or FAIL:
   - **Trace closure**: wall trace returns to origin (MUST be true)
   - **Area match**: calculated area within ±5% of official `area_m2`
   - **Collisions / bounds**: no overlapping items, nothing outside the room

4. Then report **rule findings**, grouped by severity. Each finding is formatted
   `SEVERITY RULE-ID: detail` (e.g. `ERROR CIRC-01: hall-entry→balcony-door corridor 52cm < 60cm`).
   - **ERROR** — below hard minimum
   - **WARN** — between minimum and ideal, or a violated range
   - **SKIP** — check couldn't run (missing data)

   Explain each cited rule ID in one clause so the user knows what it measures
   (e.g. "CIRC-01 is the main door-to-door route", "SEAT-01 is the sofa-to-coffee-table gap",
   "PROP-01 is sofa length vs its wall"). The canonical numbers live in
   `scripts/rules/clearances.yaml` — cite IDs, don't restate the table.

5. Turn **SKIP** lines into TODOs pointing at the phase skill that supplies the missing data:
   - No `zones:`/`circulation:`/`focal_point:` → run `/planhaus-zone`
   - Items missing `type:` → add `type:` fields to furniture/built-ins (controlled vocab)
   - TV checks skipped → add `screen_diagonal_in:`; pendant checks → add `hang_height_cm:`

6. State next actions clearly:
   - **ERRORs must be fixed before design proceeds.** A hard failure usually means looping back
     one phase (e.g. a blocked corridor revises the zone map, not just one offset).
   - **WARNs need an explicit accept-or-fix decision** — record accepted trade-offs in the
     room's notes so the review phase sees them.

## Notes

- Old projects without zones/types still validate — missing data produces SKIP, never an error.
- If the SKIPs reveal a pre-1.0 project (no `concept.yaml`, no zones anywhere, project
  CLAUDE.md without the PHASE DISCIPLINE section), suggest `/planhaus-migrate` — it upgrades
  the schemas AND retroactively derives the concept/zones the project implies.
- Floor-level collisions only — wall-mounted (`mount: wall`) and surface items (`on: base-id`) are excluded.
- Passing validation means geometry and clearances are correct, NOT that the design is good — that's `/planhaus-review`.
