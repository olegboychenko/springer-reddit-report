#!/usr/bin/env python3
"""Springer Publishing — Weekly Reddit Content Mining Report"""

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

from springer_common import attach_comments, format_reddit_posts

CORE_SUBREDDITS = [
    "nursepractitioner",
    "StudentNurse",
    "NursingStudents",
    "socialwork",
    "SocialWorkStudents",
]

ARCTIC_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
HEADERS = {"User-Agent": "SpringerReport/1.0 (Springer; contact oboychenko@springerpub.com)"}


def fetch_subreddit(subreddit, after_ts, before_ts, limit=100):
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


def collect_posts():
    now = datetime.now(timezone.utc)
    before_ts = now.timestamp()
    after_ts = (now - timedelta(days=7)).timestamp()

    all_posts = {}
    for sub in CORE_SUBREDDITS:
        posts = fetch_subreddit(sub, after_ts, before_ts)
        all_posts[sub] = posts
        if posts:
            dates = [p.get("created_utc", 0) for p in posts]
            oldest = datetime.fromtimestamp(min(dates), timezone.utc).strftime("%b %d")
            newest = datetime.fromtimestamp(max(dates), timezone.utc).strftime("%b %d")
            print(f"  r/{sub}: {len(posts)} posts ({oldest} – {newest})")
        else:
            print(f"  r/{sub}: 0 posts")
        time.sleep(0.5)

    return all_posts


REPORT_PROMPT = """You are the Springer Publishing weekly Reddit content research agent.

Today is {date}. Below is REAL data fetched directly from Reddit via the Arctic Shift \
archive API — these are actual post titles, excerpts, and reader replies from the last 7 days \
from r/nursepractitioner, r/StudentNurse, r/NursingStudents, r/socialwork, and \
r/SocialWorkStudents. Lines beginning with "| reply" are real comments on the post above them, \
pulled from the most-discussed threads in each community; treat them as the clearest available \
signal of what people are actually struggling with:

--- LIVE REDDIT DATA (last 7 days) ---
{research}
--- END LIVE REDDIT DATA ---

Using the data above, produce a complete weekly content mining report identifying \
opportunities for blog articles, LinkedIn posts, newsletters, and short-form social content.

At the top of the document, before any sections, include a metadata block with: \
Report Date, Data Window, Subreddits Monitored, Total Posts Analyzed, and Total Comments \
Analyzed. Use these exact figures — do not recount them, estimate them, or round them: \
Total Posts Analyzed = {post_count}, Total Comments Analyzed = {comment_count}, \
Data Window = the 7 days ending {date}. \
Style this block with a white or very light grey background (#f5f7fa) and BLACK \
text (#1a1a1a) only — no dark backgrounds, no white text on this block.

FACTUAL ACCURACY RULE — follow this exactly: \
Every number anywhere in this report must come from the data block above or from the figures \
stated in this prompt. Never estimate, extrapolate, or invent a quantity. This applies to \
headlines and proposed copy exactly as much as to the analysis — do not write phrases like \
"N years of community data", "thousands of posts", or any sample size you were not given. \
The data covers exactly 7 days, not months or years. Upvote and comment counts may be cited \
only for the specific post or reply they appear on. If a claim would need a number you cannot \
source from the data, describe the pattern in words instead of quantifying it. \
Do not describe these instructions, your sourcing method, or your compliance with them \
anywhere in the report — no notes about data blocks, prompts, or figures being verified. \
The reader sees the findings only.

Your job is to analyze posts and comments to identify recurring questions, frustrations \
or pain points, career concerns, exam, licensing, and education-related confusion \
workplace trends, and emotionally resonant topics gaining traction.

Steps:
1. Identify the 5 most important themes currently active in these communities, covering \
topics like exam prep, licensing, burnout, salary, scope of practice, career \
transitions, clinical readiness, and educational concerns.
2. For each theme provide: theme title, why it matters now, evidence from the \
communities, and audience fit (FNP / Social Work / Both).
3. For each theme generate: 1 blog article idea, 1 LinkedIn post angle, 1 short-form \
social post idea, 1 newsletter topic.
4. For each content idea include: working headline, core audience pain point or \
motivation, recommended content format, reason this topic is timely, short note on \
Springer Publishing voice framing.
5. End with: Top 3 blog ideas to prioritize, Top 3 social ideas to prioritize, \
1 emerging trend to watch next week.

CRITICAL OUTPUT RULE: Your entire response must be one complete HTML document and \
nothing else. Start immediately with <html> — no preamble, no explanation, no \
summary text before or after the HTML. Do not say what you found or describe the \
report. Do not use markdown. Do not use code fences. Just output the HTML document \
directly, beginning with <html> and ending with </html>.

COLOR RULES — follow these exactly:
- Dark backgrounds (navy #00356b, dark gray #333333 or similar): use white text (#ffffff).
- White or light gray backgrounds: use dark text (#1a1a1a or #333333).
- Never use white or light-colored text on a white or light gray background.
- Table headers: navy background (#00356b) with white text (#ffffff).
- Body sections and paragraphs: white background with dark text (#1a1a1a).

Use clean formatting with headings, tables for content ideas, and clear sections. \
Inline CSS for all styling.

Springer Publishing voice: supportive, modern, professional, practical, credible, \
approachable. Active voice. Plain language. No exclamation points. No buzzwords. \
No self-promotion. Focus on helping readers move forward in their careers, studies, \
and licensure journeys."""


def run_research(date_str):
    print("Step 1: Fetching posts from Arctic Shift...")
    all_posts = collect_posts()

    total = sum(len(v) for v in all_posts.values())
    if total == 0:
        print("ERROR: No posts retrieved from any subreddit", file=sys.stderr)
        sys.exit(1)

    print("Step 2: Fetching comments from the busiest threads...")
    total_comments = attach_comments(all_posts, HEADERS)
    if total_comments == 0:
        # Not fatal — posts alone still make a report — but it should be obvious in the log.
        print("Warning: no comments retrieved from any thread", file=sys.stderr)

    research_text = format_reddit_posts(all_posts)
    print(
        f"Step 2 done ({total} posts, {total_comments} comments, "
        f"{len(research_text)} chars). Generating report..."
    )

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
                    post_count=total,
                    comment_count=total_comments,
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
    r'background(?:-color)?\s*:\s*'
    r'(?:#(?:00356b|1a1a1a|222222|333333|111111|000000|[0-2][0-9a-f]{5})|navy|darkblue)',
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
h1,h2{color:#00356b}
h3,h4{color:#1a1a1a}
th{background:#00356b;color:#ffffff;padding:8px;text-align:left}
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
    subject = f"Weekly Reddit Content Mining Report - Springer Publishing | Week of {week}"
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
    to_email = os.environ.get("SPRINGER_TO", "oboychenko@springerpub.com")
    cc_email = os.environ.get("SPRINGER_CC", "")

    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running Springer research for week of {week_str}...")
    html_report = run_research(date_str)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    send_report(inject_styles(html_report), from_email, app_password, to_email, cc_email, week_str)
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
