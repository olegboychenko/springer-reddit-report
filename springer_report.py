#!/usr/bin/env python3
"""Springer Publishing — Weekly Reddit Content Mining Report"""

import os
import sys
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

PROMPT = """You are the Springer Publishing weekly Reddit content research agent.

Today is {date}. Scan and analyze recent posts and discussions from r/nursepractitioner, \
r/FNP, r/socialwork, and r/SocialWorkStudents.

Your job: identify content opportunities for blog articles, LinkedIn posts, newsletters, \
and short-form social content.

Steps:
1. Use WebSearch to find recent discussions, trending topics, questions, pain points, \
and concerns in each community. Search for topics like exam prep, licensing, burnout, \
salary, scope of practice, career transitions, and educational concerns.
2. Group findings into the 5 most important themes of the week.
3. For each theme provide: theme title, why it matters now, evidence from the \
communities, and audience fit (FNP / Social Work / Both).
4. For each theme generate: 1 blog article idea, 1 LinkedIn post angle, 1 short-form \
social post idea, 1 newsletter topic.
5. For each content idea include: working headline, core audience pain point or \
motivation, recommended content format, reason this topic is timely, short note on \
Springer Publishing voice framing.
6. End with: Top 3 blog ideas to prioritize, Top 3 social ideas to prioritize, \
1 emerging trend to watch next week.

OUTPUT FORMAT: Return the full report as a single self-contained HTML document. \
Use clean formatting with headings, tables for content ideas, and clear sections. \
No markdown — pure HTML only. Do not include code fences. Start directly with <html>.

Springer Publishing voice: supportive, modern, professional, practical, credible, \
approachable. Active voice. Plain language. No exclamation points. No buzzwords. \
No self-promotion."""


def run_research(date_str):
    result = subprocess.run(
        ["claude", "--dangerously-skip-permissions", "-p", PROMPT.format(date=date_str)],
        capture_output=True,
        text=True,
        timeout=1200,
    )
    if result.returncode != 0:
        print(f"Claude error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    output = result.stdout.strip()
    html_start = output.find("<html")
    if html_start != -1:
        return output[html_start:]
    return output


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
