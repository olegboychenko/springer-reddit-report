#!/usr/bin/env python3
"""Springer Publishing — Weekly Fertility Reddit Content Mining Report"""

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

ACCENT = "#8b1a4a"
LINK = "#8b1a4a"



CORE_SUBREDDITS = [
    "infertility",
    "IVF",
    "TryingForABaby",
    "eggfreezing",
    "PCOS",
]

HEADERS = {"User-Agent": "SpringerFertilityReport/1.0 (Springer; contact oboychenko@springerpub.com)"}


REPORT_PROMPT = """You are the Springer Publishing weekly Reddit content research agent for the fertility and reproductive health category.

Today is {date}. Below is REAL data fetched directly from Reddit via the Arctic Shift \
archive API — these are actual post titles, excerpts, and reader replies from the last 7 days \
from r/infertility, r/IVF, r/TryingForABaby, r/eggfreezing, and r/PCOS. Lines beginning with \
"| reply" are real comments on the post above them, pulled from the most-discussed threads in \
each community; treat them as the clearest available signal of what people are actually \
struggling with:

--- LIVE REDDIT DATA (last 7 days) ---
{research}
--- END LIVE REDDIT DATA ---

Using the data above, produce a complete weekly content mining report identifying \
opportunities for blog articles, social media posts, newsletters, and direct-to-consumer content.

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

The target audience is CONSUMERS — women (primarily 30–45) who are trying to conceive, \
facing age-related fertility concerns, or exploring options like IVF and egg freezing. \
This is not a clinical or professional audience. Write for someone who is anxious, \
hopeful, and looking for practical guidance and emotional reassurance.

Your job is to analyze posts and reader replies to identify recurring fears and anxieties, questions about \
age and fertility, treatment confusion (IVF, egg freezing, AMH levels, etc.), emotional \
struggles, success stories and what worked, and lifestyle and wellness questions.

Steps:
1. Identify the 5 most important themes currently active in these communities, covering \
topics like age-related fertility decline, egg quality, IVF outcomes, egg freezing \
decisions, AMH/FSH/ovarian reserve, lifestyle factors, emotional toll, and alternative \
approaches.
2. For each theme provide: theme title, why it matters now, evidence from the \
communities (cite specific post titles from the data), and emotional driver \
(fear / hope / confusion / empowerment).
3. For each theme generate: 1 blog article idea, 1 Instagram/social post angle, \
1 short-form video concept, 1 newsletter topic.
4. For each content idea include: working headline, core consumer pain point or \
motivation, recommended content format, reason this topic is timely, short note on \
brand voice framing.
5. End with: Top 3 blog ideas to prioritize, Top 3 social ideas to prioritize, \
1 emerging concern to watch next week.

CRITICAL OUTPUT RULE: Your entire response must be one complete HTML document and \
nothing else. Start immediately with <html> — no preamble, no explanation, no \
summary text before or after the HTML. Do not say what you found or describe the \
report. Do not use markdown. Do not use code fences. Just output the HTML document \
directly, beginning with <html> and ending with </html>.

COLOR RULES — follow these exactly:
- Dark backgrounds (deep rose #8b1a4a, dark gray #333333 or similar): use white text (#ffffff).
- White or light gray backgrounds: use dark text (#1a1a1a or #333333).
- Never use white or light-colored text on a white or light gray background.
- Table headers: deep rose background (#8b1a4a) with white text (#ffffff).
- Body sections and paragraphs: white background with dark text (#1a1a1a).

Use clean formatting with headings, tables for content ideas, and clear sections. \
Inline CSS for all styling.

Brand voice (based on "Yes, You Can Get Pregnant" by Aimee Raupp, published by Springer): \
hopeful and empowering without dismissing real concerns, warm and conversational, \
evidence-informed but accessible, treats the reader as a capable adult navigating a \
difficult journey. Active voice. Plain language. No exclamation points. No toxic \
positivity. No clinical coldness. Focus on agency — what the reader can do."""


def run_research(date_str):
    print("Step 1: Fetching posts from Arctic Shift...")
    all_posts = collect_posts(CORE_SUBREDDITS, HEADERS)

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
    to_email = os.environ.get("FERTILITY_TO", "oboychenko@springerpub.com")
    cc_email = os.environ.get("FERTILITY_CC", "")

    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running Fertility research for week of {week_str}...")
    html_report = run_research(date_str)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    subject = f"Weekly Fertility Reddit Intelligence Report | Week of {week_str}"
    send_report(
        inject_styles(html_report, ACCENT, LINK),
        from_email, app_password, to_email, cc_email, subject,
    )
    print(f"Report sent to {to_email}")


if __name__ == "__main__":
    main()
