---
name: planhaus-render
description: Render a room floorplan PNG and perform a mandatory visual design critique of the result
argument-hint: "<room-name>"
when_to_use: After any layout change, or whenever you need to judge how a room reads visually — focal point, balance, negative space, circulation.
allowed-tools: Bash(python3:*)
---

# Render Room Floorplan

Generate a visual floor plan PNG, then critique it like a designer.

## Steps

1. Find the room YAML file. Look for:
   - `rooms/<room-name>.yaml` in the current project directory
   - Or the exact path if the user provides one

2. Run the spatial tool to generate the floorplan:
   ```bash
   python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --plot rooms/<room-name>-floorplan.png
   ```

3. Read the generated PNG and show it to the user. Report any warnings from the tool output.

4. **MANDATORY: visual critique.** Study the PNG the way a senior designer reviews a junior's
   plan — the numbers passed, but does it *look* right? Assess:

   a. **Focal point** — is it legible at a glance? Is the seating oriented toward it, or does
      the arrangement ignore it?
   b. **Balance** — how is visual weight distributed across the plan? Is one side/corner heavy
      while another is empty?
   c. **Negative space** — where does the room breathe? Is any wall overloaded with pieces
      end-to-end (PROP-01 territory)? Is there at least one quiet moment?
   d. **Zone legibility & circulation** — do the zones read as distinct areas? Do circulation
      routes read as continuous clear paths, or do they thread awkwardly between obstacles?
   e. **Anything that looks wrong despite passing checks** — a sofa floating awkwardly mid-room,
      an orphaned chair with no relationship to anything, a rug misaligned with its group.

   Every observation must reference concrete items and positions ("the armchair at (310, 120)
   faces away from the focal window"), not vague impressions.

5. End the critique with **0–3 specific suggested moves** (item, from, to, why). Zero is a valid
   answer if the plan genuinely reads well — don't invent problems.

## Notes

- The tool requires `pyyaml` and `matplotlib`. Run `/planhaus-setup` if the SessionStart hook didn't install them.
- The PNG shows: room outline, furniture bounding boxes, windows, openings, outlets, lighting.
- Directional items (sofa, bed, TV) show a red arrow indicating facing direction.
- Re-render after any change to room YAML — the critique applies to the current state only.
