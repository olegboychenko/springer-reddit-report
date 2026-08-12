#!/usr/bin/env python3
"""Hale's Medications & Mothers' Milk — Weekly Reddit Intelligence Report"""

import os
import sys
from datetime import datetime

import anthropic

from springer_common import (
    attach_comments,
    collect_posts,
    extract_html,
    format_reddit_posts,
    inject_styles,
    send_report,
)

ACCENT = "#005a8e"
LINK = "#0066cc"



CORE_SUBREDDITS = [
    "breastfeeding",
    "beyondthebump",
    "FormulaFeeders",
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

HEADERS = {"User-Agent": "HalesReport/1.0 (Springer; contact oboychenko@springerpub.com)"}


def get_rotating_subreddit():
    week_of_month = (datetime.now().day - 1) // 7 + 1
    return ROTATING_SUBREDDITS.get(week_of_month, "Mommit")


REPORT_PROMPT = """You are the Hale's Medications & Mothers' Milk weekly Reddit intelligence analyst.

Today is {date}. Below is REAL data fetched directly from Reddit via the Arctic Shift archive \
API — these are actual post titles, excerpts, and reader replies from the last 7 days. \
Lines beginning with "| reply" are real comments on the post above them, pulled from the \
most-discussed threads in each community; treat them as the clearest available signal of \
what people are actually struggling with:

--- LIVE REDDIT DATA (last 7 days) ---
{research}
--- END LIVE REDDIT DATA ---

Produce a complete 7-section report as one HTML document.

At the top of the document, before Section 1, include a metadata block with: Report Date, \
Data Window, Subreddits Monitored, Total Posts Analyzed, and Total Comments Analyzed. \
Use these exact figures — do not recount them, estimate them, or round them: \
Total Posts Analyzed = {post_count}, Total Comments Analyzed = {comment_count}, \
Data Window = the 7 days ending {date}. Style this block with a white or very light grey background (#f5f7fa) and BLACK text (#1a1a1a) only — no dark backgrounds, no white text on this block.

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

SECTION 1 — EXECUTIVE SUMMARY
One paragraph: what this week's data tells us about the lactation/medication-safety space. \
Which communities were most active? What overarching concerns dominated?

SECTION 2 — TOP 5 THEMES OF THE WEEK
For each theme:
- Theme title
- Why it matters now (based on the posts above)
- Evidence (cite specific post titles and quote reader replies from the data)
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
    all_posts = collect_posts(CORE_SUBREDDITS + [rotating], HEADERS)

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
        model="claude-opus-4-8",
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": REPORT_PROMPT.format(
                    date=date_str,
                    research=research_text,
                    rotating=rotating,
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
    return extract_html(full_text)


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
    subject = f"Weekly Hale's Lactation & Breastfeeding Reddit Intelligence | Week of {week_str}"
    send_report(
        inject_styles(html_report, ACCENT, LINK),
        from_email, app_password, to_email, cc_email, subject,
    )
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
