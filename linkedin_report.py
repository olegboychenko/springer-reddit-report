#!/usr/bin/env python3
"""Springer Publishing — Weekly LinkedIn Content Mining Report (via Apify)"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import anthropic

from springer_common import extract_html, inject_styles, send_report

APIFY_BASE = "https://api.apify.com/v2"

APIFY_ACTOR_ID = "TODO_REPLACE_WITH_ACTOR_ID"

APIFY_INPUT = {
    "searchTerms": [
        "nurse practitioner exam prep",
        "NP board certification AANP ANCC",
        "social work licensure LCSW LMSW",
        "nursing career advice",
        "healthcare continuing education",
    ],
    "maxResults": 50,
    "dateRange": "PAST_WEEK",
}


def _api_request(method, path, body=None, token=None):
    params = f"?token={urllib.parse.quote(token)}" if token else ""
    url = f"{APIFY_BASE}{path}{params}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Warning: Apify API {method} {path} failed: {e}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"Warning: Apify request error: {e}", file=sys.stderr)
        return {}


def start_run(actor_id, input_data, token):
    return _api_request("POST", f"/acts/{actor_id}/runs", body=input_data, token=token)


def poll_run(run_id, token, timeout_seconds=300, interval=15):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        data = _api_request("GET", f"/actor-runs/{run_id}", token=token)
        status = data.get("data", {}).get("status", "")
        print(f"  Run status: {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return status, data.get("data", {})
        time.sleep(interval)
    return "TIMEOUT", {}


def fetch_dataset(dataset_id, token, limit=200):
    data = _api_request(
        "GET",
        f"/datasets/{dataset_id}/items",
        token=token,
    )
    items = data if isinstance(data, list) else data.get("data", {}).get("items", [])
    return items[:limit]


def collect_data(token):
    print("  Starting Apify actor run...")
    run_data = start_run(APIFY_ACTOR_ID, APIFY_INPUT, token)
    run_id = run_data.get("data", {}).get("id")
    if not run_id:
        print("ERROR: Could not start Apify run", file=sys.stderr)
        return []

    print(f"  Run ID: {run_id}. Polling for completion...")
    status, run_info = poll_run(run_id, token)
    if status != "SUCCEEDED":
        print(f"ERROR: Apify run ended with status {status}", file=sys.stderr)
        return []

    dataset_id = run_info.get("defaultDatasetId")
    if not dataset_id:
        print("ERROR: No dataset ID in run result", file=sys.stderr)
        return []

    print(f"  Fetching dataset {dataset_id}...")
    return fetch_dataset(dataset_id, token)


def format_data(posts):
    if not posts:
        return "No posts retrieved."
    lines = []
    for p in posts:
        author = p.get("authorName") or p.get("author", "Unknown")
        text = (p.get("text") or p.get("content") or "")[:400].strip()
        likes = p.get("numLikes") or p.get("likes", 0)
        comments = p.get("numComments") or p.get("comments", 0)
        date = (p.get("postedAt") or p.get("date", ""))[:10]
        lines.append(f"\n[{likes} likes | {comments} comments | {date}] {author}")
        if text:
            lines.append(f"  {text}")
    return "\n".join(lines)


REPORT_PROMPT = """You are the Springer Publishing weekly LinkedIn content research agent.

Today is {date}. Below is REAL data fetched from LinkedIn via the Apify scraping platform — \
these are actual posts from nursing, nurse practitioner, social work, and healthcare \
education communities from the last 7 days:

--- LIVE LINKEDIN DATA (last 7 days) ---
{research}
--- END LIVE LINKEDIN DATA ---

Using the data above, produce a complete weekly content mining report identifying \
opportunities for blog articles, LinkedIn posts, newsletters, and short-form social content.

At the top of the document, before any sections, include a metadata block with: \
Report Date, Data Window, Search Terms Used, and Total Posts Analyzed. \
Style this block with a white or very light grey background (#f5f7fa) and BLACK \
text (#1a1a1a) only — no dark backgrounds, no white text on this block.

Your job is to analyze post text and engagement metrics to identify recurring questions, \
frustrations or pain points, career concerns, exam and licensing confusion, workplace \
trends, and emotionally resonant topics gaining traction.

Steps:
1. Identify the 5 most important themes currently active in these communities, covering \
topics like exam prep, licensing, burnout, salary, scope of practice, career \
transitions, clinical readiness, and educational concerns.
2. For each theme provide: theme title, why it matters now, evidence from the posts, \
and audience fit (FNP / Social Work / Both).
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


def run_research(date_str, token):
    print("Step 1: Fetching posts from LinkedIn via Apify...")
    posts = collect_data(token)

    if not posts:
        print("ERROR: No posts retrieved", file=sys.stderr)
        sys.exit(1)

    research_text = format_data(posts)
    print(f"Step 1 done ({len(posts)} posts, {len(research_text)} chars). Generating report...")

    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": REPORT_PROMPT.format(date=date_str, research=research_text)}],
    ) as stream:
        report_msg = stream.get_final_message()

    full_text = "".join(block.text for block in report_msg.content if block.type == "text")
    return extract_html(full_text)


def main():
    apify_token = os.environ.get("APIFY_API_TOKEN")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    from_email = os.environ.get("SPRINGER_FROM", "oleg.boychenko73@gmail.com")
    to_email = os.environ.get("SPRINGER_TO", "oboychenko@springerpub.com")
    cc_email = os.environ.get("SPRINGER_CC", "")

    if not apify_token:
        print("ERROR: APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running Springer LinkedIn research for week of {week_str}...")
    html_report = run_research(date_str, apify_token)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    subject = f"Weekly LinkedIn Content Mining Report - Springer Publishing | Week of {week_str}"
    send_report(inject_styles(html_report), from_email, app_password, to_email, cc_email, subject)
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
