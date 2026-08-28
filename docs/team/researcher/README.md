# researcher workspace

**Cadence:** Sat 10:00 IST.

## Weekly research digest (Saturday)

File: `docs/team/researcher/weekly_<YYYY-MM-DD>.md`.

Researcher uses Gemini 2.5 Pro (1M context) to read long-form quant
literature and synthesize feature ideas relevant to the open R&D priority
list in CLAUDE.md ("Open R&D priorities" section).

Each week pick ONE of:

- **Literature scan** — pull 3-5 recent (last 6 months) papers/posts from
  arXiv, Hudson & Thames, Quantpedia, MQL5 forum, or Wilmott. Summarize
  each in 2-3 sentences. Identify 1-2 ideas that could land in
  `FEATURE_COLS_V2` next.

- **Walkforward analysis** — run `tools/walkforward_lab.py --symbol all`
  over the past 30 days of bars and compare to the prior 30 days. Flag
  symbols/teams where edge has decayed >2 percentage points.

- **Replay study** — pick a recent trade (or a recent vetoed signal) from
  `recent_results` and trace the full feature/gate path. Note any feature
  whose contribution looks brittle.

Format every digest with:

```
# Research digest — week of <YYYY-MM-DD>
## Top finding
<2 sentences>
## Detail
<3-6 bullets>
## Next action
<one-sentence handoff to architect or operator>
```

After writing, append a `research` event to the handoff log. If a finding
warrants an immediate architect action, add a `requires_operator` event
referencing this file.

## Don'ts

- No book reviews. Recent (< 6 months) work only.
- No magic-bullet claims. If something seems too good, sanity-check and
  surface the suspicion explicitly.
- Don't recommend retraining on its own — that's the architect's call.
