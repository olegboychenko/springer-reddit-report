#!/usr/bin/env python3
"""Springer Publishing — shared utilities for all report agents."""

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def extract_html(full_text):
    """Slice from the first <html tag onward; return the full text if not found."""
    idx = full_text.find("<html")
    return full_text[idx:].strip() if idx != -1 else full_text.strip()


_DARK_BG_DEFAULT = re.compile(
    r'background(?:-color)?\s*:\s*'
    r'(?:#(?:00356b|1a1a1a|222222|333333|111111|000000|[0-2][0-9a-f]{5})|navy|darkblue)',
    re.IGNORECASE,
)


def fix_contrast(html, dark_bg_re=None):
    """Ensure white text on any dark-background element."""
    pattern = dark_bg_re if dark_bg_re is not None else _DARK_BG_DEFAULT

    def process(m):
        tag = m.group(0)
        tag_name = m.group(1).lower()
        is_th = tag_name == "th"
        has_dark_bg = bool(pattern.search(tag))
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


def inject_styles(html, accent="#00356b"):
    html = fix_contrast(html)
    css = f"""<style>
body{{color:#1a1a1a;background:#ffffff;font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:24px}}
h1,h2{{color:{accent}}}
h3,h4{{color:#1a1a1a}}
th{{background:{accent};color:#ffffff;padding:8px;text-align:left}}
td{{padding:8px;vertical-align:top}}
tr:nth-child(even){{background:#f5f7fa}}
a{{color:#0066cc}}
</style>"""
    if "<head>" in html:
        return html.replace("<head>", "<head>" + css, 1)
    if "<html>" in html:
        return html.replace("<html>", "<html><head>" + css + "</head>", 1)
    return css + html


def send_report(html_body, from_email, app_password, to_email, cc_email, subject):
    """Send an HTML report via Gmail SMTP_SSL."""
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
