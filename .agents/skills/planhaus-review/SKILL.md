---
name: planhaus-review
description: Adversarial design review of a room or the whole apartment against the design checklist — verdict per item with evidence and rule IDs
argument-hint: "<room-name|apartment>"
when_to_use: At the end of a design phase, after major layout or FF&E changes, or when the user asks "is this good?" — runs as a forked design-reviewer critique.
context: fork
agent: planhaus-design-reviewer
allowed-tools: Bash(python3:*)
---

# Design Review

You are reviewing this project as an adversarial design critic. Your job is to find what's
wrong — never rubber-stamp. The instructions below stand alone: follow them whether you are
running as the forked `design-reviewer` agent or inline in the main session.

## Inputs

1. **Checklist**: prefer the project's own `design-checklist.yaml`; if absent, fall back to
   `"tools/planhaus/templates/design-checklist.yaml"`. Use its numeric thresholds where
   given (e.g. density metric, 3–5 material count).
2. **Concept**: `concept.yaml` (if present) and `brief.yaml`.
3. **Rooms**: `rooms/<room>.yaml` for the target room, or `apartment.yaml` + all room files for
   an apartment review. Registry items referenced by the rooms.
4. **Floorplans**: read the `rooms/<room>-floorplan.png` images — judge what the plan *looks*
   like, not just the numbers.

## Steps

1. **Re-run the spatial check yourself** — do not trust stale validation notes. Call the script
   directly (never invoke other skills via slash-command syntax):
   ```bash
   python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --check
   ```
   For an apartment review, run it for every room. Use `--matrix` when you need distances as
   evidence.

2. **Single room** (`/planhaus-review living-room`): assess each `per_room` checklist item —
   density (compute the floor-coverage metric), focal point, flow, light, breathing room.

3. **Apartment** (`/planhaus-review apartment`): assess each `per_apartment` item — material
   palette (count unique materials), transitions, sightlines, style thread, hierarchy.

4. **Concept coherence**: check that what's actually placed and registered follows
   `concept.yaml` — palette roles (60-30-10), master material list, style signals, avoid-list,
   room hierarchy vs design emphasis. Flag every divergence from the brief's stated direction.

5. **Verdict per checklist item**: `pass` / `warn` / `fail`, each with concrete evidence —
   positions, measurements, rule IDs (e.g. "fail — WARN CIRC-02: sofa→dining route 62cm,
   ideal 75cm"). No verdict without evidence.

6. Separate findings into three sections: **violations** (rule/threshold failures),
   **judgment concerns** (subjective but specific), **what works** (kept short). End with the
   checklist's reflective questions and your overall verdict.

## Notes

- Accepted WARNs documented in room notes are not violations — verify the note exists, then
  treat them as recorded trade-offs.
- Old projects without `concept.yaml`/zones still get a review — skip those checks and say so.
