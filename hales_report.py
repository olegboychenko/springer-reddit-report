#!/usr/bin/env python3
"""Hale's Medications & Mothers' Milk — Weekly Reddit Intelligence Report"""

import json
import os
import re
import sys
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

CORE_SUBREDDITS = [
    "breastfeeding",
    "beyondthebump",
    "HumanForMula",
    "NewParents",
    "lactation",
]

ROTATING_SUBREDDITS = {
    1: "pharmacy",
    2: "nursing",
    3: "Postpartum_Depression",
    4: "Mommit",
    5: "Midwives",
}

ARCTIC_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
HEADERS = {"User-Agent": "HalesReport/1.0 (Springer; contact oboychenko@springerpub.com)"}


def get_rotating_subreddit():
    week_of_month = (datetime.now().day - 1) // 7 + 1
    return ROTATING_SUBREDDITS.get(week_of_month, "Mommit")


def fetch_subreddit(subreddit, after_ts, before_ts, limit=50):
    params = urllib.parse.urlencode({
        "subreddit": subreddit,
        "after": int(after_ts),
        "before": int(before_ts),
        "limit": limit,
    })
    req = urllib.request.Request(f"{ARCTIC_URL}?{params}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except urllib.error.HTTPError as e:
        print(f"Warning: could not fetch r/{subreddit}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Warning: r/{subreddit} error: {e}", file=sys.stderr)
        return []


def collect_posts(rotating):
    now = datetime.now(timezone.utc)
    before_ts = now.timestamp()
    after_ts = (now - timedelta(days=7)).timestamp()

    all_posts = {}
    for sub in CORE_SUBREDDITS + [rotating]:
        posts = fetch_subreddit(sub, after_ts, before_ts)
        all_posts[sub] = posts
        print(f"  r/{sub}: {len(posts)} posts")
        time.sleep(0.5)

    return all_posts


def format_posts(all_posts):
    lines = []
    for sub, posts in all_posts.items():
        lines.append(f"\nr/{sub} ({len(posts)} posts, last 7 days):")
        for p in posts[:20]:
            score = p.get("score", 0)
            title = p.get("title", "").strip()
            comments = p.get("num_comments", 0)
            snippet = (p.get("selftext") or "")[:200].strip()
            lines.append(f"  [{score}up {comments} comments] {title}")
            if snippet:
                lines.append(f"    > {snippet}")
    return "\n".join(lines) if lines else "No posts retrieved."


REPORT_PROMPT = """You are the Hale's Medications & Mothers' Milk weekly Reddit intelligence analyst.

Today is {date}. Below is REAL data fetched directly from Reddit via the Arctic Shift archive \
API — these are actual post titles and excerpts from the last 7 days:

--- LIVE REDDIT DATA (last 7 days) ---
{research}
--- END LIVE REDDIT DATA ---

Produce a complete 7-section report as one HTML document.

SECTION 1 — EXECUTIVE SUMMARY
One paragraph: what this week's data tells us about the lactation/medication-safety space. \
Which communities were most active? What overarching concerns dominated?

SECTION 2 — TOP 5 THEMES OF THE WEEK
For each theme:
- Theme title
- Why it matters now (based on the posts above)
- Evidence (cite specific post titles from the data)
- Audience fit: Clinicians / Patients / Both

SECTION 3 — CONTENT OPPORTUNITIES (table)
For each theme, rows with columns:
Content Type | Working Headline | Audience Pain Point | Format | Timeliness Note | Hale's Voice Framing
Content types per theme: Blog Article, LinkedIn Post, Short-Form Social, Newsletter Topic

SECTION 4 — COMMUNITY SIGNALS
- Most-asked medication or drug-class questions this week
- Recurring fears or misconceptions spotted
- Gaps in available resources (what people could not find answers to)

SECTION 5 — CLINICIAN VS. PATIENT LENS
Two columns: what clinicians/HCPs were discussing vs. what patients/new parents were discussing

SECTION 6 — PRIORITIZATION
- Top 3 blog ideas to act on this week (with brief rationale)
- Top 3 social content ideas (with brief rationale)
- 1 emerging topic to monitor next week

SECTION 7 — ROTATING COMMUNITY SPOTLIGHT
This week's rotating subreddit: r/{rotating}
What did this community contribute that the core subreddits did not?

Use clean formatting with headings, tables for content ideas, and clear sections. \
Inline CSS for styling is encouraged.

Hale's voice: evidence-based, reassuring, precise, practical. Written for both clinicians who \
need accuracy and new parents who need clarity. No exclamation points. No buzzwords. Active voice.

CRITICAL OUTPUT RULE: Your entire response must be one complete HTML document and nothing else. \
Start immediately with <html> — no preamble, no explanation, no text before or after the HTML. \
Do not use markdown. Do not use code fences. Output the HTML document directly, \
beginning with <html> and ending with </html>.

Do not add any disclaimer or caveat about data availability. Use the post titles and themes \
above to generate specific, actionable content recommendations."""


def run_research(date_str, rotating):
    print("Step 1: Fetching posts from Arctic Shift...")
    all_posts = collect_posts(rotating)

    total = sum(len(v) for v in all_posts.values())
    if total == 0:
        print("ERROR: No posts retrieved from any subreddit", file=sys.stderr)
        sys.exit(1)

    research_text = format_posts(all_posts)
    print(f"Step 1 done ({total} posts, {len(research_text)} chars). Generating report...")

    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": REPORT_PROMPT.format(
                    date=date_str,
                    research=research_text,
                    rotating=rotating,
                ),
            }
        ],
    ) as stream:
        report_msg = stream.get_final_message()

    full_text = "".join(
        block.text for block in report_msg.content if block.type == "text"
    )
    html_start = full_text.find("<html")
    if html_start != -1:
        return full_text[html_start:].strip()
    return full_text.strip()


DARK_BG = re.compile(
    r'background(?:-color)?\s*:\s*(?:#(?:005a8e|1a1a1a|222222|333333|111111|000000|[0-2][0-9a-f]{5})|navy|darkblue)',
    re.IGNORECASE,
)


def fix_contrast(html):
    def process(m):
        tag = m.group(0)
        tag_name = m.group(1).lower()
        is_th = tag_name == "th"
        has_dark_bg = bool(DARK_BG.search(tag))
        if not is_th and not has_dark_bg:
            return tag
        if re.search(r"(?i)(?<![a-z-])color\s*:", tag):
            tag = re.sub(r"(?i)(?<![a-z-])(color\s*:\s*)[^;}'\"]+", r"\g<1>#ffffff", tag)
        elif re.search(r'(?i)style\s*=\s*"', tag):
            tag = re.sub(r'(?i)(style\s*=\s*")', r"\1color:#ffffff;", tag)
        else:
            tag = tag[:-1] + ' style="color:#ffffff;">'
        return tag

    return re.sub(r"<(th|h[1-6]|div|p|span|li|td)\b[^>]*>", process, html, flags=re.IGNORECASE)


def inject_styles(html):
    html = fix_contrast(html)
    css = """<style>
body{color:#1a1a1a;background:#ffffff;font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:24px}
h1,h2{color:#005a8e}
h3,h4{color:#1a1a1a}
th{background:#005a8e;color:#ffffff;padding:8px;text-align:left}
td{padding:8px;vertical-align:top}
tr:nth-child(even){background:#f5f7fa}
a{color:#0066cc}
</style>"""
    if "<head>" in html:
        return html.replace("<head>", "<head>" + css, 1)
    if "<html>" in html:
        return html.replace("<html>", "<html><head>" + css + "</head>", 1)
    return css + html


def send_report(html_body, from_email, app_password, to_email, cc_email, week):
    subject = f"Weekly Hale's Lactation & Breastfeeding Reddit Intelligence | Week of {week}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    if cc_email:
        msg["Cc"] = cc_email
    msg.attach(MIMEText(html_body, "html"))
    recipients = [to_email] + ([cc_email] if cc_email else [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, recipients, msg.as_string())


def main():
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    from_email = os.environ.get("SPRINGER_FROM", "oleg.boychenko73@gmail.com")
    to_email = os.environ.get("HALES_TO", "oboychenko@springerpub.com")
    cc_email = os.environ.get("HALES_CC", "")

    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")
    rotating = get_rotating_subreddit()

    print(f"Running Hale's research for week of {week_str} (rotating: r/{rotating})...")

    html_report = run_research(date_str, rotating)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    send_report(inject_styles(html_report), from_email, app_password, to_email, cc_email, week_str)
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
