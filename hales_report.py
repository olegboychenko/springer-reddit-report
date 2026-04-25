#!/usr/bin/env python3
"""Hale's Medications & Mothers' Milk — Weekly Reddit Intelligence Report"""

import json
import os
import re
import sys
import time
import smtplib
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import anthropic

CORE_SUBREDDITS = [
    "breastfeeding",
    "HumanForMula",
    "beyondthebump",
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


def get_rotating_subreddit():
    week_of_month = (datetime.now().day - 1) // 7 + 1
    return ROTATING_SUBREDDITS.get(week_of_month, "Mommit")


def fetch_posts(subreddit_name, days=7, limit=100):
    cutoff = time.time() - days * 24 * 3600
    url = f"https://www.reddit.com/r/{subreddit_name}/new.json?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HalesReportBot/1.0 (weekly content research)"},
    )
    posts = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        for child in data["data"]["children"]:
            p = child["data"]
            if p["created_utc"] < cutoff:
                continue
            entry = f"[{p['score']}↑ {p['num_comments']} comments] {p['title']}"
            if p.get("selftext"):
                entry += f"\n{p['selftext'][:400]}"
            posts.append(entry)
    except Exception as e:
        print(f"Warning: could not fetch r/{subreddit_name}: {e}", file=sys.stderr)
    return posts


def build_context():
    rotating = get_rotating_subreddit()
    all_subreddits = CORE_SUBREDDITS + [rotating]

    sections = []
    for name in all_subreddits:
        posts = fetch_posts(name)
        label = f"r/{name}" + (" [rotating this week]" if name == rotating else "")
        if posts:
            sections.append(
                f"### {label} ({len(posts)} posts this week)\n" + "\n".join(posts[:30])
            )
        else:
            sections.append(f"### {label}\n(no posts retrieved)")
        time.sleep(1)  # stay within Reddit's rate limit

    return "\n\n".join(sections), rotating


PROMPT = """You are the Hale's Medications & Mothers' Milk weekly Reddit intelligence analyst.

Today is {date}. Below are REAL Reddit posts from the past 7 days across lactation and new-parent communities. Analyze them and produce the weekly intelligence report.

--- LIVE REDDIT DATA ---
{reddit_context}
--- END REDDIT DATA ---

Based on the posts above, produce a complete 7-section HTML report:

SECTION 1 — EXECUTIVE SUMMARY
One paragraph: what this week's data tells us about the lactation/medication-safety space. Which communities were most active? What overarching concerns dominated?

SECTION 2 — TOP 5 THEMES OF THE WEEK
For each theme:
- Theme title
- Why it matters now (based on the actual posts above)
- Evidence (reference specific post titles or discussion patterns from the data)
- Audience fit: Clinicians / Patients / Both

SECTION 3 — CONTENT OPPORTUNITIES (table)
For each theme, one row per content type with columns:
Content Type | Working Headline | Audience Pain Point | Format | Timeliness Note | Hale's Voice Framing
Content types per theme: Blog Article, LinkedIn Post, Short-Form Social, Newsletter Topic

SECTION 4 — COMMUNITY SIGNALS
- Most-asked medication or drug-class questions this week
- Recurring fears or misconceptions spotted
- Gaps in available resources (what people could not find answers to)

SECTION 5 — CLINICIAN VS. PATIENT LENS
Split the week's key discussion themes into two columns:
- What clinicians and HCPs were discussing
- What patients and new parents were discussing

SECTION 6 — PRIORITIZATION
- Top 3 blog ideas to act on this week (with brief rationale)
- Top 3 social content ideas (with brief rationale)
- 1 emerging topic to monitor next week

SECTION 7 — ROTATING COMMUNITY SPOTLIGHT
This week's rotating subreddit: r/{rotating_subreddit}
What did this community contribute that the core subreddits did not? Any unique angles, terminology, or concerns?

CRITICAL OUTPUT RULE: Your entire response must be one complete HTML document and nothing else. Start immediately with <html> — no preamble, no explanation, no summary text before or after the HTML. Do not describe the report. Do not use markdown. Do not use code fences. Output the HTML document directly, beginning with <html> and ending with </html>.

Use clean formatting with headings, tables for content ideas, and clear sections. Inline CSS for styling is encouraged.

Hale's voice: evidence-based, reassuring, precise, practical. Written for both clinicians who need accuracy and new parents who need clarity. No exclamation points. No buzzwords. Active voice. Focus on medication safety, lactation science, and clinical decision support."""


def run_research(date_str, reddit_context, rotating_subreddit):
    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": PROMPT.format(
                date=date_str,
                reddit_context=reddit_context,
                rotating_subreddit=rotating_subreddit,
            ),
        }],
    ) as stream:
        message = stream.get_final_message()

    full_text = "".join(
        block.text for block in message.content if block.type == "text"
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

    print(f"Running Hale's research for week of {week_str}...")
    print("Fetching live Reddit posts...")
    reddit_context, rotating = build_context()
    print(f"Fetched Reddit data. Rotating subreddit this week: r/{rotating}")
    print("Running analysis...")

    html_report = run_research(date_str, reddit_context, rotating)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    send_report(inject_styles(html_report), from_email, app_password, to_email, cc_email, week_str)
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
