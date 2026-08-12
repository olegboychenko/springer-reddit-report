# CLAUDE.md — Springer Publishing Weekly Content Research Pipeline

This repo runs weekly content-research agents for Springer Publishing. Each agent pulls
7 days of community data from a platform, sends it to Claude for analysis, and emails a
styled HTML report. Read this file before making changes. Match the existing patterns —
do not introduce new ones without flagging the tradeoff first.

## Architecture (every agent follows this exact shape)

```
GitHub Actions (weekly cron + workflow_dispatch)
  → fetch  (platform API, stdlib urllib only)
  → format (flatten to a plain-text block for the prompt)
  → analyze (Claude, streaming, returns one full HTML document)
  → post-process HTML (enforce contrast + inject Springer styles)
  → email  (Gmail SMTP_SSL, multipart HTML, To + optional Cc)
```

Each report = one workflow file + one Python script. Keep them parallel and independent.
(Several reports share a source — three of the five pull from Reddit — so the unit is the
report, not the platform.)

## Files

**Layout convention:** GitHub Actions workflow files MUST live in `.github/workflows/`
(Actions only runs workflows from that exact path — never the repo root). Python scripts
live at the repo root. `.github/` is a hidden directory, so read it by explicit path.

**Naming convention:** `<topic>_report.py` at the repo root + `<topic>-report.yml` in
`.github/workflows/`. (`fertility_report.yml` uses an underscore — the one holdout. Leave it:
renaming a workflow file creates a new entry in the Actions UI and detaches its run history.)

Live (scheduled and running — read the Reddit pair first, it is the reference implementation):
- `.github/workflows/springer-report.yml` + `springer_report.py` — Reddit, Arctic Shift API
- `.github/workflows/youtube-report.yml` + `youtube_report.py` — YouTube Data API v3
- `.github/workflows/hales-report.yml` + `hales_report.py` — Reddit, Arctic Shift API
  (Hale's Medications & Mothers' Milk — lactation and breastfeeding)
- `.github/workflows/fertility_report.yml` + `fertility_report.py` — Reddit, Arctic Shift API
  (fertility: r/infertility, r/IVF, r/TryingForABaby, r/eggfreezing, r/PCOS)

On hold (built, deliberately not live):
- `.github/workflows/linkedin-report.yml` + `linkedin_report.py` — Apify actor (paid).
  The cron is commented out and `APIFY_ACTOR_ID` is still `TODO_REPLACE_WITH_ACTOR_ID`, so only
  `workflow_dispatch` is available and it will fail at the first API call until that ID is set.
  This is intentional, not a bug. No Apify spend has occurred.

Shared:
- `springer_common.py` — `extract_html()`, `fix_contrast()`, `inject_styles()`, `send_report()`.
  Imported by `youtube_report.py` and `linkedin_report.py`. `springer_report.py`,
  `hales_report.py`, and `fertility_report.py` still carry their own local copies of these
  helpers; that duplication is known debt, not a pattern to follow. New scripts import from
  `springer_common.py` — do not copy-paste. Propose the layout before refactoring the three
  scripts that still duplicate.

New workflow files go in `.github/workflows/`, NOT the repo root — a `.yml` placed at the
root will silently never trigger. New Python scripts go at the root next to `springer_report.py`.

## Hard conventions — do not deviate

- **Dependencies:** pure Python stdlib for fetching and email (`urllib`, `json`, `smtplib`,
  `email`, `datetime`). The ONLY pip install is `anthropic`. Don't add `requests`, `praw`,
  Google client libs, or an Apify SDK — call the REST endpoints with `urllib`.
- **Model call:** `client.messages.stream(model="claude-opus-4-8", max_tokens=16000, ...)`,
  a single user message. Extract text blocks, then slice from the first `<html` onward.
  Opus is the default for new scripts. Migration status: `fertility_report.py` is on
  `claude-opus-4-8`; `springer_report.py`, `youtube_report.py`, `hales_report.py`, and
  `linkedin_report.py` still call `claude-sonnet-4-6` and are pending migration.
- **Output contract:** the model must return ONE complete HTML document and nothing else —
  no markdown, no code fences, no preamble. The prompt enforces this; keep that instruction.
- **HTML post-processing:** always run `springer_common.fix_contrast()` + `inject_styles()`
  before sending. These guarantee the Springer palette and accessible contrast regardless of
  model output. `springer_common.py` holds the canonical implementations — import them.
  (`springer_report.py`, `hales_report.py`, and `fertility_report.py` still define their own
  identical copies; keep any fix in sync across all four until they are consolidated.)
- **Source rotation:** `hales_report.py` fetches five fixed subreddits plus one that rotates by
  week of month (`ROTATING_SUBREDDITS`). This is a Hale's-only pattern, not a repo convention —
  don't copy it into other reports, and don't delete it as an anomaly.
- **Error handling:** every per-source fetch is wrapped so a failure logs a warning to stderr
  and returns `[]` — one bad source must never crash the whole run. If the total result count
  across all sources is zero, exit non-zero so the run visibly fails.
- **Time window:** rolling 7 days computed from `datetime.now(timezone.utc)`.
- **Encoding:** scripts run with `-X utf8` and `PYTHONIOENCODING: utf-8` in the workflow.

## Secrets & environment

Set via GitHub repo secrets — **never write keys, tokens, or passwords into any file.**
If a new secret is needed, tell me the exact `gh secret set` command to run; don't hardcode.

- `ANTHROPIC_API_KEY` — Claude API (all reports)
- `GMAIL_APP_PASSWORD` — Gmail app password for SMTP send (all reports)
- `YOUTUBE_API_KEY` — YouTube report (live)
- `APIFY_API_TOKEN` — LinkedIn report (on hold; set, but the report does not run)

Non-secret env vars (fine to keep in the workflow file):
- `SPRINGER_FROM` = oleg.boychenko73@gmail.com — sender for every report
- `SPRINGER_TO` = oboychenko@springerpub.com / `SPRINGER_CC` = abennie@springerpub.com
  — Reddit, YouTube, LinkedIn
- `HALES_TO` = oboychenko@springerpub.com / `HALES_CC` = vgarcia@springerpub.com — Hale's
- `FERTILITY_TO` = oboychenko@springerpub.com / `FERTILITY_CC` = vgarcia@springerpub.com
  — Fertility

Each report reads its own To/Cc pair, so a new report needs its own `<TOPIC>_TO` /
`<TOPIC>_CC` rather than reusing `SPRINGER_TO`.

## Email

`smtplib.SMTP_SSL("smtp.gmail.com", 465)`, login with `SPRINGER_FROM` + `GMAIL_APP_PASSWORD`,
multipart/alternative with an HTML part.

Two subject-line shapes are in use. Match the one for the product line the report belongs to:
- Springer-branded reports (Reddit, YouTube, LinkedIn):
  `Weekly <Platform> Content Mining Report - Springer Publishing | Week of <date>`
- Product-line reports (Fertility, Hale's), which carry no Springer branding in the subject:
  `Weekly Fertility Reddit Intelligence Report | Week of <date>`
  `Weekly Hale's Lactation & Breastfeeding Reddit Intelligence | Week of <date>`

## Report color rules (enforced in HTML + post-processing)

- Dark backgrounds (navy `#00356b`, dark gray `#333333`): white text `#ffffff`.
- White / light gray backgrounds: dark text `#1a1a1a` or `#333333`.
- Never light text on a light background.
- Table headers: navy `#00356b` background, white text.
- Top metadata block: light grey `#f5f7fa` background with black `#1a1a1a` text.

## Springer brand voice (applies to all report copy the model generates)

Supportive, modern, professional, practical, credible, approachable. Active voice, plain
language, short sentences. Sentence case. No exclamation points, no buzzwords, no
self-promotion, no clickbait, no meme/hot-take angles. Focus on helping readers move forward
in their careers, studies, and licensure journeys. Favor educational, practical, career-helpful
content over reactive takes.

## Scheduling

Weekly, Monday mornings, with `workflow_dispatch` always enabled for manual test runs.
Stagger crons so jobs don't fire simultaneously. Current schedule (all UTC, all Monday):

| Report | Cron | Status |
|---|---|---|
| Reddit | `30 9 * * 1` | live |
| YouTube | `35 9 * * 1` | live |
| Hale's | `0 10 * * 1` | live |
| Fertility | `0 11 * * 1` | live |
| LinkedIn | `40 9 * * 1` | commented out — on hold |

Give a new report its own slot rather than reusing one of these. Always test via
`workflow_dispatch` before trusting the cron.

## Security restrictions

- Never commit secrets or print them to logs.
- Never email to addresses other than the To/Cc configured for that report's own workflow
  (`SPRINGER_TO`/`SPRINGER_CC`, `HALES_TO`/`HALES_CC`, `FERTILITY_TO`/`FERTILITY_CC`). The only
  addresses in use today are oboychenko@springerpub.com, abennie@springerpub.com, and
  vgarcia@springerpub.com.
- Cap external API result volume to control cost. The paid Apify run is capped at
  `APIFY_INPUT["maxResults"] = 50` with a 300s poll timeout — written but never yet executed,
  since the LinkedIn report has not gone live.
- Don't add network calls to domains beyond the platform APIs, the Anthropic API, and Gmail SMTP.
