---
name: planhaus-new-project
description: Scaffold a new interior design project from templates
argument-hint: "<project-name>"
disable-model-invocation: true
---

# New Project

Create a new interior design project with all required files.

## Steps

1. Parse the project name from the argument. If no name given, ask the user.

2. Copy the template directory to create the project:
   ```bash
   cp -r "tools/planhaus/templates/" <project-name>/
   ```

3. The new project will contain:
   - `CLAUDE.md` — design rules and conventions
   - `brief.yaml` — client profile template (programming phase input)
   - `concept.yaml` — design concept template (narrative, style, palette, budget)
   - `apartment.yaml` — apartment layout template
   - `rooms/_template.yaml` — room specification template
   - `registry/_template.yaml` — product registry template
   - `design-checklist.yaml` — design integration checklist
   - `workflow.md` — data collection workflow

4. Point the user at the phase sequence — each phase produces a checkable artifact:
   1. Fill `brief.yaml` (or run `/planhaus-brief` for a guided intake interview)
   2. `/planhaus-concept` — translate the brief into `concept.yaml`
   3. Per room: `/planhaus-zone` — fixed features, focal point, zones + circulation
   4. `/planhaus-furnish` — anchor-first placement inside the zones
   5. `/planhaus-select` — per furniture slot, pick the actual piece
   6. `/planhaus-light` — 3-layer lighting plan
   7. `/planhaus-review` — adversarial review against the checklist

## Notes

- The CLAUDE.md contains all design conventions and coordinate system rules.
- brief.yaml is client input only — keep it high-level, no room-level specs.
- Never place furniture before zones and circulation exist; never select FF&E before the layout fixes dimensions.
- For each room, copy `rooms/_template.yaml` to `rooms/<room-name>.yaml`.
- For each product candidate, copy `registry/_template.yaml` to `registry/<category>/<item>.yaml`.
