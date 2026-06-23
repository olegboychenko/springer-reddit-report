#!/usr/bin/env python3
"""Springer Publishing — Weekly YouTube Content Mining Report"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import anthropic

from springer_common import extract_html, inject_styles, send_report

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

SEARCH_QUERIES = [
    "nurse practitioner exam prep AANP ANCC",
    "NP board exam study tips",
    "social work LCSW LMSW exam",
    "nursing licensure NCLEX tips",
    "nurse practitioner career advice",
    "social work career licensure continuing education",
]


def _get(url, params):
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Warning: YouTube API error {e.code} for {url}: {e}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"Warning: YouTube request failed: {e}", file=sys.stderr)
        return {}


def search_videos(query, api_key, published_after, max_results=25):
    data = _get(f"{YOUTUBE_API_BASE}/search", {
        "part": "id,snippet",
        "q": query,
        "type": "video",
        "publishedAfter": published_after,
        "maxResults": max_results,
        "relevanceLanguage": "en",
        "key": api_key,
    })
    items = data.get("items", [])
    return [
        {
            "video_id": item["id"].get("videoId", ""),
            "title": item["snippet"].get("title", ""),
            "channel": item["snippet"].get("channelTitle", ""),
            "published": item["snippet"].get("publishedAt", ""),
            "description": item["snippet"].get("description", "")[:200],
        }
        for item in items
        if item.get("id", {}).get("videoId")
    ]


def fetch_video_details(video_ids, api_key):
    """Batch-fetch statistics for up to 50 video IDs at a time."""
    results = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        data = _get(f"{YOUTUBE_API_BASE}/videos", {
            "part": "statistics,contentDetails",
            "id": ",".join(batch),
            "key": api_key,
        })
        for item in data.get("items", []):
            stats = item.get("statistics", {})
            results[item["id"]] = {
                "views": stats.get("viewCount", "0"),
                "likes": stats.get("likeCount", "0"),
                "comments": stats.get("commentCount", "0"),
            }
        time.sleep(0.3)
    return results


def fetch_comments(video_id, api_key, max_results=10):
    """Fetch top comments for a video; silently skip on 403 (disabled comments)."""
    data = _get(f"{YOUTUBE_API_BASE}/commentThreads", {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": max_results,
        "key": api_key,
    })
    if not data:
        return []
    comments = []
    for item in data.get("items", []):
        top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        text = top.get("textDisplay", "").strip()
        if text:
            comments.append(text[:300])
    return comments


def collect_data(api_key):
    now = datetime.now(timezone.utc)
    published_after = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_videos = []
    seen_ids = set()

    for query in SEARCH_QUERIES:
        videos = search_videos(query, api_key, published_after)
        for v in videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
        print(f"  Query '{query[:40]}': {len(videos)} videos")
        time.sleep(0.5)

    if not all_videos:
        return []

    video_ids = [v["video_id"] for v in all_videos]
    details = fetch_video_details(video_ids, api_key)

    for v in all_videos:
        stats = details.get(v["video_id"], {})
        v["views"] = stats.get("views", "0")
        v["likes"] = stats.get("likes", "0")
        v["comment_count"] = stats.get("comments", "0")

    top_videos = sorted(all_videos, key=lambda x: int(x.get("views", 0)), reverse=True)[:30]

    for v in top_videos[:10]:
        v["top_comments"] = fetch_comments(v["video_id"], api_key)
        time.sleep(0.3)

    return top_videos


def format_data(videos):
    if not videos:
        return "No videos retrieved."
    lines = []
    for v in videos:
        lines.append(
            f"\n[{v['views']} views | {v['likes']} likes | {v['comment_count']} comments]"
            f" {v['title']} — {v['channel']} ({v['published'][:10]})"
        )
        if v.get("description"):
            lines.append(f"  Description: {v['description']}")
        for c in v.get("top_comments", []):
            lines.append(f"  Comment: {c}")
    return "\n".join(lines)


REPORT_PROMPT = """You are the Springer Publishing weekly YouTube content research agent.

Today is {date}. Below is REAL data fetched from YouTube via the YouTube Data API v3 — \
these are actual video titles, engagement metrics, and viewer comments from the last 7 days \
across nursing, nurse practitioner, social work, and licensure exam topics:

--- LIVE YOUTUBE DATA (last 7 days) ---
{research}
--- END LIVE YOUTUBE DATA ---

Using the data above, produce a complete weekly content mining report identifying \
opportunities for blog articles, LinkedIn posts, newsletters, and short-form social content.

At the top of the document, before any sections, include a metadata block with: \
Report Date, Data Window, Search Queries Used, and Total Videos Analyzed. \
Style this block with a white or very light grey background (#f5f7fa) and BLACK \
text (#1a1a1a) only — no dark backgrounds, no white text on this block.

Your job is to analyze video titles, view counts, and viewer comments to identify \
recurring questions, frustrations or pain points, career concerns, exam and licensing \
confusion, workplace trends, and emotionally resonant topics gaining traction.

Steps:
1. Identify the 5 most important themes currently active in these communities, covering \
topics like exam prep, licensing, burnout, salary, scope of practice, career \
transitions, clinical readiness, and educational concerns.
2. For each theme provide: theme title, why it matters now, evidence from the videos and \
comments, and audience fit (FNP / Social Work / Both).
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


def run_research(date_str, api_key):
    print("Step 1: Fetching videos from YouTube Data API...")
    videos = collect_data(api_key)

    if not videos:
        print("ERROR: No videos retrieved", file=sys.stderr)
        sys.exit(1)

    research_text = format_data(videos)
    print(f"Step 1 done ({len(videos)} videos, {len(research_text)} chars). Generating report...")

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
    api_key = os.environ.get("YOUTUBE_API_KEY")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    from_email = os.environ.get("SPRINGER_FROM", "oleg.boychenko73@gmail.com")
    to_email = os.environ.get("SPRINGER_TO", "oboychenko@springerpub.com")
    cc_email = os.environ.get("SPRINGER_CC", "")

    if not api_key:
        print("ERROR: YOUTUBE_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running Springer YouTube research for week of {week_str}...")
    html_report = run_research(date_str, api_key)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    subject = f"Weekly YouTube Content Mining Report - Springer Publishing | Week of {week_str}"
    send_report(inject_styles(html_report), from_email, app_password, to_email, cc_email, subject)
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
