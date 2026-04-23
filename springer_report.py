#!/usr/bin/env python3
"""Springer Publishing — Weekly Reddit Content Mining Report"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

import anthropic

PROMPT = """You are the Springer Publishing weekly Reddit content research agent.

Today is {date}. Your job is to scan and analyze recent posts and discussions from \
r/nursepractitioner, r/FNP, r/socialwork, and r/SocialWorkStudents, then identify \
content opportunities for blog articles, LinkedIn posts, newsletters, and short-form \
social content.

Steps:
1. Use web_search to find recent discussions, trending topics, questions, pain points, \
and concerns in each community. Run multiple searches — search each subreddit by name, \
and search for topics like exam prep, licensing, burnout, salary, scope of practice, \
career transitions, and educational concerns. Aim for at least 8 searches total to \
ensure broad coverage.
2. Group findings into the 5 most important themes of the week.
3. For each theme provide: theme title, why it matters now, evidence from the \
communities (specific posts or discussion patterns observed), and audience fit \
(FNP / Social Work / Both).
4. For each theme generate: 1 blog article idea, 1 LinkedIn post angle, 1 short-form \
social post idea, 1 newsletter topic.
5. For each content idea include: working headline, core audience pain point or \
motivation, recommended content format, reason this topic is timely, short note on \
Springer Publishing voice framing.
6. End with: Top 3 blog ideas to prioritize, Top 3 social ideas to prioritize, \
1 emerging trend to watch next week.

OUTPUT FORMAT: Return the full report as a single self-contained HTML document. \
Use clean formatting with headings, tables for content ideas, and clear sections. \
No markdown — pure HTML only. Do not include ```html code fences. \
Start directly with <html>.

Springer Publishing voice: supportive, modern, professional, practical, credible, \
approachable. Active voice. Plain language. No exclamation points. No buzzwords. \
No self-promotion. Focus on helping readers move forward in their careers, studies, \
and licensure journeys."""


def run_research(date_str):
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": PROMPT.format(date=date_str)}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            html_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return "".join(html_parts).strip()

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "",
                })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            html_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return "".join(html_parts).strip()


def send_report(html_body, api_key, from_email, to_email, week):
    subject = (
        f"Weekly Reddit Content Mining Report — Springer Publishing | Week of {week}"
    )

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Report sent to {to_email} — status {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR {e.code}: {body}", file=sys.stderr)
        sys.exit(1)


def main():
    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("SPRINGER_FROM", "oleg.boychenko73@gmail.com")
    to_email = os.environ.get("SPRINGER_TO", "oboychenko@springerpub.com")

    if not api_key:
        print("ERROR: SENDGRID_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running research for week of {week_str}...")
    html_report = run_research(date_str)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via SendGrid...")
    send_report(html_report, api_key, from_email, to_email, week_str)


if __name__ == "__main__":
    main()
