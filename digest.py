#!/usr/bin/env python3
"""Daily email digest: new strong matches from data/jobs.json. Stdlib only.
Needs secrets SMTP_USER, SMTP_APP_PASSWORD (a Gmail app password) and DIGEST_TO. Without them it does nothing.
Already-mailed job ids are kept in data/digest_sent.json so nobody is mailed twice."""
import json, os, smtplib, ssl, sys
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape

ROOT = os.path.dirname(os.path.abspath(__file__))
MIN_SCORE, MAX_JOBS = 70, 15
RORDER = {"tunisia": 0, "khalij": 1, "remote": 2, "europe": 3, "other": 4}
LABEL = {"tunisia": "Tunisia", "khalij": "Gulf", "remote": "Remote", "europe": "Europe", "other": "Other"}
DASH = os.environ.get("DASHBOARD_URL", "https://akramhentati0-glitch.github.io/job-radar/")


def main():
    user, pw, to = (os.environ.get(k, "").strip() for k in ("SMTP_USER", "SMTP_APP_PASSWORD", "DIGEST_TO"))
    if not (user and pw and to):
        print("digest: SMTP_USER / SMTP_APP_PASSWORD / DIGEST_TO not set, skipping"); return 0
    jobs = json.load(open(os.path.join(ROOT, "data", "jobs.json"), encoding="utf-8")).get("jobs", [])
    sent_path = os.path.join(ROOT, "data", "digest_sent.json")
    sent = set(json.load(open(sent_path))) if os.path.exists(sent_path) else set()
    fresh = [j for j in jobs if j["score"] >= MIN_SCORE and j["id"] not in sent]
    if not fresh:
        print("digest: nothing new to send"); return 0
    fresh.sort(key=lambda j: (RORDER.get(j["region"], 4), -j["score"]))
    top = fresh[:MAX_JOBS]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    msg = EmailMessage()
    msg["Subject"] = f"Job Radar: {len(fresh)} new strong match{'es' if len(fresh) != 1 else ''} ({day})"
    msg["From"], msg["To"] = user, to
    lines, rows = [], []
    for j in top:
        tags = [LABEL.get(j["region"], j["region"])] + (["visa/relocation"] if "visa/relocation" in j["why"] else []) \
            + (["junior-friendly"] if "junior-friendly" in j["why"] else [])
        lines.append(f"[{j['score']}] {j['title']} - {j['company']} ({j['location']}) | {', '.join(tags)}\n    {j['url']}")
        rows.append(f"<p style='margin:0 0 14px'><b>{j['score']}</b> &nbsp;<a href='{escape(j['url'])}'>{escape(j['title'])}</a><br>"
                    f"<span style='color:#555'>{escape(j['company'])} · {escape(j['location'])} · {escape(', '.join(tags))}</span></p>")
    more = f"\n+ {len(fresh) - len(top)} more in the dashboard." if len(fresh) > len(top) else ""
    msg.set_content("New strong matches (score 70+), Tunisia first:\n\n" + "\n".join(lines) + more + f"\n\nDashboard: {DASH}\n")
    msg.add_alternative("<div style='font-family:system-ui,sans-serif;font-size:15px'><p>New strong matches (score 70+), Tunisia first:</p>"
                        + "".join(rows) + (f"<p style='color:#555'>+ {len(fresh) - len(top)} more in the dashboard.</p>" if more else "")
                        + f"<p><a href='{escape(DASH)}'>Open the dashboard</a></p></div>", subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(user, pw); s.send_message(msg)
    json.dump(sorted(sent | {j["id"] for j in fresh}), open(sent_path, "w"))
    print(f"digest: emailed {len(top)} of {len(fresh)} new matches")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # an email problem must never break the daily update
        print(f"digest: FAILED {type(e).__name__}: {e}"); sys.exit(0)
