---
name: planhaus-brief
description: Guided client intake interview that produces brief.yaml — household, mood, taste (LOVE/HATE), priorities, numeric budget, constraints, reference URLs. Use when starting a design brief, when the user describes what they want from their home, or when brief.yaml is empty or missing.
argument-hint: "[project-dir]"
---

# Client Brief (Phase 1 — Programming)

Interview the client and write `brief.yaml` — the project's north star. Every later phase
traces back to it.

**Reads**: existing `brief.yaml` if present (then this is an update interview). Structure mirrors `templates/brief.yaml`.
**Writes**: `brief.yaml` in the project root.
**Back-edge**: none — this is phase 1. Unanswerable questions get a `# TODO` comment in the file, never an invented answer.

## How to interview

Conversational, in small batches of 2–3 questions. Wait for answers before the next batch.
Reflect answers back ("so weekday evenings the living room is mostly the two of you reading?").

**Push past vague answers.** Adjectives mean nothing until pinned down:
- "Warm" → warm how? Materials (wood, linen)? Light (low 2700K glow)? Color (terracotta, ochre)?
- "Modern" → which modern? Clean-lined Scandinavian? Midcentury? Minimal concrete-and-glass?
- "Cozy" → small enclosed nooks, or soft textures in an open space?

Ask for a concrete example or a reference photo whenever an answer stays abstract.

## Question batches

1. **Household & activities** — who lives here (adults / kids / pets), work-from-home (days/week
   + equipment), guests (who, how often), rental plans, daily routines, special needs
   (allergies, mobility, light sleeper, left-handed desk user).
2. **Mood & taste** — 3–6 adjectives for the feeling; LOVE list and HATE list (the HATE list is
   gold — it becomes the concept's avoid-list); any standing challenge (views, awkward geometry);
   reference URLs (designers, hotels, shops) with one note each on WHY they like it.
3. **Priorities** — must have / important / nice to have. Force a ranking if everything is "must".
4. **Budget** — a NUMERIC total + currency (non-negotiable; if they hesitate, offer ranges:
   "closer to 10k or 30k?"), quality level (e.g. "Zara Home / Kave Home baseline"), where to
   splurge (1–2 items), where to save.
5. **Constraints** — what cannot change: built-ins, floors, finishes, landlord rules, existing
   furniture that stays.
6. **Shops & references** — preferred shop URLs; consolidate the reference URLs from batch 2.

## Writing brief.yaml

Follow the structure of `templates/brief.yaml` exactly (`about_us`, `mood`, `taste`,
`priorities`, `budget`, `constraints`, `shops`, `references`). The `budget` section is a
mapping with a numeric total:

```yaml
budget:
  total: 25000            # numeric — /planhaus-concept allocates from this
  currency: EUR
  notes: |
    Quality level, where to splurge, where to save (client's words).
```

Record the client's words (cleaned up), not your interpretations — interpretation happens in
`/planhaus-concept`. Keep it high-level: no room-level specs, no product picks.

## Notes

- `budget.total` and `budget.currency` are optional-but-recommended: old projects with a
  free-text budget block still work, but `/planhaus-concept` will ask for a number before
  allocating budget.
- If `brief.yaml` already exists, read it first and only interview the gaps; summarize what
  changed and warn that a changed brief means re-checking `concept.yaml`.
- End by summarizing the brief in ~5 lines for client confirmation, then suggest: `/planhaus-concept`.
