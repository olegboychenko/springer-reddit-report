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

Each platform = one workflow file + one Python script. Keep them parallel and independent.

## Files

**Layout convention:** GitHub Actions workflow files MUST live in `.github/workflows/`
(Actions only runs workflows from that exact path — never the repo root). Python scripts
live at the repo root. `.github/` is a hidden directory, so read it by explicit path.

Existing (the reference implementation — read these first):
- `.github/workflows/springer-report.yml` — Reddit workflow
- `springer_report.py` — Reddit fetch/analyze/email script (Arctic Shift API)

Planned (build these to match):
- `.github/workflows/springer-report-youtube.yml` + `springer_report_youtube.py` — YouTube Data API v3
- `.github/workflows/springer-report-linkedin.yml` + `springer_report_linkedin.py` — Apify actor (paid)

New workflow files go in `.github/workflows/`, NOT the repo root — a `.yml` placed at the
root will silently never trigger. New Python scripts go at the root next to `springer_report.py`.

If shared logic emerges (HTML post-processing, email send, prompt scaffolding), factor it
into `springer_common.py` rather than copy-pasting across scripts. Propose the layout before
refactoring.

## Hard conventions — do not deviate

- **Dependencies:** pure Python stdlib for fetching and email (`urllib`, `json`, `smtplib`,
  `email`, `datetime`). The ONLY pip install is `anthropic`. Don't add `requests`, `praw`,
  Google client libs, or an Apify SDK — call the REST endpoints with `urllib`.
- **Model call:** `client.messages.stream(model="claude-sonnet-4-6", max_tokens=16000, ...)`,
  a single user message. Extract text blocks, then slice from the first `<html` onward.
- **Output contract:** the model must return ONE complete HTML document and nothing else —
  no markdown, no code fences, no preamble. The prompt enforces this; keep that instruction.
- **HTML post-processing:** always run the equivalent of `fix_contrast()` + `inject_styles()`
  before sending. These guarantee the Springer palette and accessible contrast regardless of
  model output. Reuse this logic verbatim across agents.
- **Error handling:** every per-source fetch is wrapped so a failure logs a warning to stderr
  and returns `[]` — one bad source must never crash the whole run. If the total result count
  across all sources is zero, exit non-zero so the run visibly fails.
- **Time window:** rolling 7 days computed from `datetime.now(timezone.utc)`.
- **Encoding:** scripts run with `-X utf8` and `PYTHONIOENCODING: utf-8` in the workflow.

## Secrets & environment

Set via GitHub repo secrets — **never write keys, tokens, or passwords into any file.**
If a new secret is needed, tell me the exact `gh secret set` command to run; don't hardcode.

- `ANTHROPIC_API_KEY` — Claude API
- `GMAIL_APP_PASSWORD` — Gmail app password for SMTP send
- `YOUTUBE_API_KEY` — (new, for the YouTube agent)
- `APIFY_API_TOKEN` — (new, for the LinkedIn agent)

Non-secret env vars (fine to keep in the workflow file):
- `SPRINGER_FROM` = oleg.boychenko73@gmail.com
- `SPRINGER_TO` = oboychenko@springerpub.com
- `SPRINGER_CC` = abennie@springerpub.com

## Email

`smtplib.SMTP_SSL("smtp.gmail.com", 465)`, login with `SPRINGER_FROM` + `GMAIL_APP_PASSWORD`,
multipart/alternative with an HTML part. Subject line follows the existing format:
`Weekly <Platform> Content Mining Report - Springer Publishing | Week of <date>`.

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
Stagger crons so the three jobs don't fire simultaneously (e.g. Reddit `30 9`, YouTube `35 9`,
LinkedIn `40 9` — all `* * 1` UTC). Always test a new agent via `workflow_dispatch` before
trusting the cron.

## Security restrictions

- Never commit secrets or print them to logs.
- Never email to addresses other than the configured `SPRINGER_TO` / `SPRINGER_CC`.
- Cap external API result volume (especially the paid Apify run) to control cost.
- Don't add network calls to domains beyond the platform APIs, the Anthropic API, and Gmail SMTP.
