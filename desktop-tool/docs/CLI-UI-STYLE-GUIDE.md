# Desktop Tool CLI UI Style Guide

## Scope

This guide defines the output style for the desktop tool CLI so new UI changes stay consistent across contributors and AI coding runs.

Goals:
- Keep output understandable for non-technical users.
- Separate prompts, status, progress, and action-required messages.
- Keep one primary focus on screen at a time.

Dependency policy:
- Prefer currently installed UI libraries (`InquirerPy`, `click`, `enlighten`) for all CLI UI work.
- Do not add a new UI library without explicit user approval first.

## UX Model

Use phase-based output with clear transitions:
1. `Setup`
2. `Plan Summary`
3. `Running`
4. `Waiting on You`
5. `Done`

Each phase should print a short header before any detailed lines.

## Message Types

Use these labels consistently:
- `[QUESTION]` user input needed now.
- `[INFO]` normal progress information.
- `[PROGRESS]` counters/bars only.
- `[ACTION REQUIRED]` explicit manual step in browser.
- `[STATE]` current internal state in one concise line.
- `[DONE]` completion and next steps.

Do not invent additional labels without updating this guide.

## Prompt Rules

- During prompt mode, do not print progress bars or noisy logs.
- For startup onboarding prompts, keep wording short and predictable.
- Include defaults and fallback guidance: `Default: X. If you're not sure, press Enter.`
- Ask only relevant questions:
  - If site is `DriveThruCards`, skip `auto-save`.
  - If site is `DriveThruCards`, skip image post-processing question and set post-processing to disabled.

## Progress Rules

- Show progress bars only in `Running` phase.
- Keep bar names stable:
  - `Images Downloaded`
  - `Images Uploaded`
  - `Projects Auto-Filled`
- On phase change or action-required pause, clear/suspend redraw so bars do not overlap with plain text.
- When a bar reaches completion, either:
  - hide it and include a one-line summary, or
  - keep it in a fixed progress block without interleaving other messages.

## State Line

- Keep exactly one state line visible for humans:
  - Example: `[STATE] Defining Order - Awaiting user sign-in`
- Avoid printing internal state repeatedly unless it changes.

## Formatting

- Use blank lines between sections.
- Prefer short lines and plain language.
- Avoid stacked paragraphs while automation is active.

Recommended section order in active runs:
1. Phase header
2. Current task line
3. Action-required block (only when needed)
4. Progress block
5. State line

## Mockup A Reference (Target Shape)

```text
┌──────────────────────────────────────────────────────────────┐
│ MPC Autofill                                                 │
│ Phase: Setup (1/5)                                           │
└──────────────────────────────────────────────────────────────┘

[QUESTION 1/4] Browser
Default: chrome (press Enter if unsure)

  1) chrome   (default)
  2) brave
  3) edge
  4) firefox

Select: _
```

```text
┌──────────────────────────────────────────────────────────────┐
│ MPC Autofill                                                 │
│ Phase: Running (3/5)                                         │
│ Current step: Uploading fronts                               │
└──────────────────────────────────────────────────────────────┘

[PROGRESS]
Images Downloaded     [████████████████████] 3/3
Images Uploaded       [███.................] 1/3
Projects Auto-Filled  [....................] 0/1

[STATE] Defining Order
```

## Logging Policy

- Default log level should remain concise.
- Detailed diagnostic output belongs to debug mode only.
- Never let debug lines break prompt readability.

## Change Control

Before merging CLI UI changes:
1. Verify prompts do not interleave with progress redraw.
2. Verify DriveThruCards conditional question flow.
3. Run onboarding-focused tests.
4. Capture one terminal transcript for a non-DTC run and one DTC run.
