#!/usr/bin/env python3
"""Springer Publishing — Weekly Reddit Content Mining Report"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import anthropic

RESEARCH_PROMPT = """Today is {date}. Search Reddit and related sources for recent \
discussions in r/nursepractitioner, r/FNP, r/socialwork, and r/SocialWorkStudents.

Run at least 8 searches covering: trending topics, exam prep, licensing issues, \
burnout, salary, scope of practice, career transitions, and educational concerns.

After all searches, write a thorough plain-text summary of what you found: key themes, \
specific discussions or posts observed, and what practitioners and students are most \
concerned about this week. Be specific and detailed."""

REPORT_PROMPT = """You are producing a weekly content mining report for Springer Publishing.

Based on these research findings:

{research}

Create a report with:
1. The 5 most important themes of the week. For each theme: title, why it matters now, \
evidence from the communities, audience fit (FNP / Social Work / Both).
2. For each theme: 1 blog article idea, 1 LinkedIn post angle, 1 short-form social post \
idea, 1 newsletter topic.
3. For each content idea: working headline, core audience pain point, recommended format, \
timeliness rationale, Springer voice framing note.
4. End with: Top 3 blog ideas, Top 3 social ideas, 1 emerging trend to watch next week.

Springer voice: supportive, professional, practical, plain language, no exclamation \
points, no buzzwords, no self-promotion.

Output a single complete HTML document with clean formatting, tables for content ideas, \
and clear sections. Use inline CSS."""


def run_research(date_str):
    client = anthropic.Anthropic()

    # Step 1: Research using web search
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": RESEARCH_PROMPT.format(date=date_str)}],
    ) as stream:
        research_message = stream.get_final_message()

    research_text = "".join(
        block.text for block in research_message.content if block.type == "text"
    )

    # Step 2: Generate HTML report from research findings (no tools)
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system="You are an HTML document generator. Your entire response must be a single valid HTML document. Start with <html> and end with </html>. Output no other text whatsoever.",
        messages=[{"role": "user", "content": REPORT_PROMPT.format(research=research_text)}],
    ) as stream:
        report_message = stream.get_final_message()

    full_text = "".join(
        block.text for block in report_message.content if block.type == "text"
    )
    html_start = full_text.find("<html")
    if html_start != -1:
        return full_text[html_start:].strip()
    return full_text.strip()


def inject_styles(html):
    css = """<style>
body{color:#1a1a1a!important;background:#ffffff!important;font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:24px}
h1,h2{color:#00356b!important}
h3,h4{color:#1a1a1a!important}
p,li,td,span,div{color:#1a1a1a!important}
th{background:#00356b!important;color:#ffffff!important;padding:8px;text-align:left}
td{color:#1a1a1a!important;padding:8px;vertical-align:top}
tr:nth-child(even){background:#f5f7fa}
a{color:#0066cc!important}
</style>"""
    if "<head>" in html:
        return html.replace("<head>", "<head>" + css, 1)
    if "<html>" in html:
        return html.replace("<html>", "<html><head>" + css + "</head>", 1)
    return css + html


def send_report(html_body, from_email, app_password, to_email, week):
    subject = (
        f"Weekly Reddit Content Mining Report - Springer Publishing | Week of {week}"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, to_email, msg.as_string())
        print(f"Report sent to {to_email}")


def main():
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    from_email = os.environ.get("SPRINGER_FROM", "oleg.boychenko73@gmail.com")
    to_email = os.environ.get("SPRINGER_TO", "oboychenko@springerpub.com")

    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    week_str = now.strftime("%B %d, %Y")

    print(f"Running research for week of {week_str}...")
    html_report = run_research(date_str)

    if not html_report:
        print("ERROR: Empty report generated", file=sys.stderr)
        sys.exit(1)

    print(f"Report generated ({len(html_report):,} chars). Sending via Gmail...")
    send_report(inject_styles(html_report), from_email, app_password, to_email, week_str)


if __name__ == "__main__":
    main()
