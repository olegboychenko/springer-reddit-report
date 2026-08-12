#!/usr/bin/env python3
"""Springer Publishing — shared utilities for all report agents."""

import json
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# --- Reddit comment fetching (shared by the three Arctic Shift reports) -------------

ARCTIC_COMMENTS_URL = "https://arctic-shift.photon-reddit.com/api/comments/search"

COMMENT_POSTS_PER_SUB = 5
COMMENT_FETCH_POOL = 25   # request this many per thread...
COMMENTS_PER_POST = 6     # ...then keep this many after filtering, best-scored first
COMMENT_MAX_CHARS = 300
# The busiest threads skew to "I passed!" and weekly check-in posts, where replies are
# congratulations rather than content. Requiring some length drops those without
# hand-maintaining a phrase blocklist.
COMMENT_MIN_CHARS = 80
SKIP_COMMENT_AUTHORS = {"AutoModerator"}
SKIP_COMMENT_BODIES = {"[deleted]", "[removed]", ""}
POSTS_RENDERED_PER_SUB = 35


def fetch_comments(post, headers, keep=COMMENTS_PER_POST):
    """Fetch top-level discussion for one post. Returns [] on any failure.

    Over-fetches and then filters: asking for only `keep` comments means a thread whose
    first replies are all one-liners yields almost nothing after filtering.
    """
    link_id = post.get("name") or (f"t3_{post['id']}" if post.get("id") else "")
    if not link_id:
        return []

    params = urllib.parse.urlencode({"link_id": link_id, "limit": COMMENT_FETCH_POOL})
    req = urllib.request.Request(f"{ARCTIC_COMMENTS_URL}?{params}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read()).get("data", [])
    except urllib.error.HTTPError as e:
        print(f"Warning: could not fetch comments for {link_id}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Warning: comments for {link_id} error: {e}", file=sys.stderr)
        return []

    comments = []
    for c in data:
        body = (c.get("body") or "").strip()
        if body in SKIP_COMMENT_BODIES or c.get("author") in SKIP_COMMENT_AUTHORS:
            continue
        if len(body) < COMMENT_MIN_CHARS:
            continue
        comments.append({"score": c.get("score", 0), "body": body[:COMMENT_MAX_CHARS]})

    comments.sort(key=lambda c: c["score"], reverse=True)
    return comments[:keep]


def pick_comment_threads(posts):
    """Choose which threads to pull discussion from.

    Stickied posts are the weekly check-in and megathread slots — high comment counts,
    almost no content — so they are excluded outright.
    """
    candidates = [
        p for p in posts
        if p.get("num_comments", 0) > 0 and not p.get("stickied")
    ]
    candidates.sort(key=lambda p: p.get("num_comments", 0), reverse=True)
    return candidates[:COMMENT_POSTS_PER_SUB]


def attach_comments(all_posts, headers):
    """Attach comments to the most-discussed threads in each subreddit.

    Per-subreddit rather than global so one loud community can't crowd out the others.
    """
    total = 0
    for sub, posts in all_posts.items():
        targets = pick_comment_threads(posts)
        fetched = 0
        productive = 0
        for post in targets:
            post["comments"] = fetch_comments(post, headers)
            fetched += len(post["comments"])
            productive += 1 if post["comments"] else 0
            time.sleep(0.4)
        total += fetched
        print(f"  r/{sub}: {fetched} comments from {productive}/{len(targets)} threads")
    return total


def select_render_posts(posts):
    """The first N posts, plus any post carrying comments.

    Threads picked for comment fetching are the highest num_comments in the whole
    100-post window, so they routinely fall outside the first N. Without this union
    their comments are fetched and then silently dropped before reaching the prompt.
    """
    keep = set(range(min(POSTS_RENDERED_PER_SUB, len(posts))))
    keep.update(i for i, p in enumerate(posts) if p.get("comments"))
    return [posts[i] for i in sorted(keep)]


def format_reddit_posts(all_posts):
    """Flatten posts and their fetched replies into the plain-text prompt block."""
    lines = []
    for sub, posts in all_posts.items():
        lines.append(f"\nr/{sub} ({len(posts)} posts, last 7 days):")
        for p in select_render_posts(posts):
            score = p.get("score", 0)
            title = p.get("title", "").strip()
            comments = p.get("num_comments", 0)
            snippet = (p.get("selftext") or "")[:200].strip()
            lines.append(f"  [{score}up {comments} comments] {title}")
            if snippet:
                lines.append(f"    > {snippet}")
            for c in p.get("comments", []):
                lines.append(f"    | reply ({c['score']}up): {c['body']}")
    return "\n".join(lines) if lines else "No posts retrieved."


# --- HTML + email ------------------------------------------------------------------


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
