# Talking points for presenting this project

A quick script for walking an interviewer through this project — useful for
an Amazon BA loop's "tell me about a project" / bar-raiser conversations,
or a portfolio walkthrough.

## 30-second version

"I built a feedback analytics dashboard modeled on the kind of reporting my
team — Copilot Feedback Analytics — would build for our Image Upload
surface. It tracks sentiment (positive/negative/neutral feedback rate),
a recognition-accuracy proxy, resolution time, and which issue categories
are driving negative feedback. The data refreshes automatically once a day
via a scheduled job, so it behaves like a real reporting pipeline instead
of a static one-off chart."

## If asked "why these metrics?"

- **Feedback volume** alone is a vanity metric — it tells you engagement,
  not health. Positive/negative *rate* normalizes for that.
- **Recognition accuracy** is the leading indicator; sentiment is the
  lagging one. Tracking both side by side is how you catch a quality
  regression before complaints spike.
- **Resolution time** turns "we know what's wrong" into "we're
  accountable for fixing it" — it's an operational metric, not just an
  analytical one.
- **Category breakdown** is what makes the dashboard *actionable*: a PM
  looking at "40% negative" doesn't know what to do next; a PM looking at
  "missed objects is the #1 driver, 3x the next category" does.

## If asked "how would you validate this with real data?"

- Cross-check the recognition-accuracy proxy against actual model eval
  metrics (precision/recall on a labeled holdout set) — feedback sentiment
  is a noisy proxy for model quality, not a substitute for it.
- Check for reporting bias: users who had a bad experience are more likely
  to leave feedback at all, so raw sentiment rate probably overstates the
  negative share relative to all uploads. Uploads-processed vs.
  feedback-given ratio (also in the dataset) is one way to sanity check
  that.
- Segment by region/device/cohort before trusting an aggregate trend —
  the dashboard's region breakdown is a first step toward that.

## If asked "what would you change for production?"

- Swap `generate_daily_data.py` for a real ETL step (nightly export from
  the actual feedback store into the same JSON shape) — the front end
  wouldn't need to change.
- Add statistical significance / confidence bounds to day-over-day deltas
  rather than reading noise as signal.
- Add drill-down (click a category → see example feedback text, if privacy
  policy allows) so the dashboard supports root-causing, not just
  monitoring.
- Add alerting (e.g., negative rate crosses a threshold) instead of relying
  on someone opening the dashboard.

## Design decisions worth mentioning

- Chose a **rolling window + idempotent regeneration** for the dataset
  instead of an ever-growing file, so the repo and the daily CI diff stay
  small — same trade-off you'd make with a real data warehouse retention
  policy.
- Kept the dashboard **static (no backend)** so it deploys for free on
  GitHub Pages and has zero infrastructure to maintain — appropriate for a
  portfolio piece, and a real trade-off you'd surface in a design review
  ("do we need a live backend, or does a scheduled batch refresh meet the
  actual latency requirement?").
