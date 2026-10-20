#!/usr/bin/env python3
"""job-radar: fetch -> normalise -> filter -> score -> data/jobs.json. Stdlib only."""
import hashlib, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from html import unescape

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
UA = {"User-Agent": "job-radar/1.0 (personal job search; github.com/akramhentati0-glitch/job-radar)", "Accept": "application/json"}


def http(url, data=None, headers=None, timeout=25):
    h = dict(UA); h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    if body: h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_text(url, timeout=25):
    h = dict(UA); h["Accept"] = "text/plain, text/markdown, */*"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def strip(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def job(source, id_, title, company, location, desc, url, posted, remote=False):
    return {"source": source, "src_id": str(id_), "title": strip(title), "company": strip(company),
            "location": strip(location), "description": strip(desc)[:4000], "url": url,
            "posted": posted, "remote": bool(remote)}


def to_iso(v):
    if v is None or v == "": return None
    try:
        if isinstance(v, (int, float)): return datetime.fromtimestamp(v, timezone.utc).isoformat()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "T", 1)).astimezone(timezone.utc).isoformat()
    except Exception:
        return None

# ---------------- sources ----------------
def f_arbeitnow():
    out = []
    for page in (1, 2, 3):
        d = http(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        for j in d.get("data", []):
            out.append(job("arbeitnow", j["slug"], j["title"], j["company_name"], j.get("location", ""),
                           j.get("description", ""), j["url"], to_iso(j.get("created_at")), j.get("remote")))
    return out


def f_jobtech():
    out = []
    for q in CFG["search_queries"][:4]:
        d = http("https://jobsearch.api.jobtechdev.se/search?" + urllib.parse.urlencode({"q": q, "limit": 50}))
        for h in d.get("hits", []):
            a = h.get("workplace_address") or {}
            out.append(job("jobtech", h["id"], h.get("headline", ""), (h.get("employer") or {}).get("name", ""),
                           f"{a.get('municipality') or ''}, Sweden", (h.get("description") or {}).get("text", ""),
                           h.get("webpage_url") or f"https://arbetsformedlingen.se/platsbanken/annonser/{h['id']}",
                           to_iso(h.get("publication_date"))))
    return out


def f_remotive():
    d = http("https://remotive.com/api/remote-jobs?category=software-dev&limit=200")
    return [job("remotive", j["id"], j["title"], j["company_name"], j.get("candidate_required_location", "Remote"),
                j.get("description", ""), j["url"], to_iso(j.get("publication_date")), True) for j in d.get("jobs", [])]


def f_jobicy():
    d = http("https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev")
    return [job("jobicy", j["id"], j["jobTitle"], j["companyName"], j.get("jobGeo", "Remote"),
                j.get("jobExcerpt", "") + " " + str(j.get("jobLevel", "")), j["url"], to_iso(j.get("pubDate")), True)
            for j in d.get("jobs", [])]


def f_jooble(cfg):
    key = os.environ.get("JOOBLE_KEY")
    if not key: raise RuntimeError("JOOBLE_KEY not set (free key at jooble.org/api/about)")
    out = []
    for country in cfg["countries"]:
        for q in CFG["search_queries"][:3]:
            d = http(f"https://jooble.org/api/{key}", {"keywords": q, "location": country, "page": 1})
            for j in d.get("jobs", []):
                out.append(job("jooble", j.get("id") or j["link"], j["title"], j.get("company", ""),
                               j.get("location") or country, j.get("snippet", ""), j["link"], to_iso(j.get("updated"))))
            time.sleep(0.3)
    return out


def f_adzuna(cfg):
    i, k = os.environ.get("ADZUNA_ID"), os.environ.get("ADZUNA_KEY")
    if not (i and k): raise RuntimeError("ADZUNA_ID/ADZUNA_KEY not set (free at developer.adzuna.com)")
    out = []
    for c in cfg["countries"]:
        d = http(f"https://api.adzuna.com/v1/api/jobs/{c}/search/1?" + urllib.parse.urlencode(
            {"app_id": i, "app_key": k, "what": "software developer junior", "results_per_page": 50, "max_days_old": CFG["max_age_days"]}))
        for j in d.get("results", []):
            out.append(job("adzuna", j["id"], j["title"], (j.get("company") or {}).get("display_name", ""),
                           (j.get("location") or {}).get("display_name", "") + f", {c.upper()}",
                           j.get("description", ""), j["redirect_url"], to_iso(j.get("created"))))
    return out

# ---- Keejob (Tunisia). Uses the site's own published machine-readable list (llms-full.txt) and the
# per-offer Markdown pages it links to. No HTML scraping, no search URLs, a few requests per run.
KJ_LINE = re.compile(r"^- \[(.+?)\]\((https://www\.keejob\.com/offres-emploi/(\d+)/[^)\s]+?)\.md\): (.*)$")
KJ_MODES = {"sur site", "hybride", "télétravail", "teletravail"}
KJ_TECH = re.compile(r"d[ée]velop|informatique|software|full.?stack|front|back.?end|devops|data|\bia\b|\bai\b|"
                     r"cyber|r[ée]seau|syst[èe]me|\bqa\b|\btest|\bux\b|\bui\b|web|mobile|\berp\b|\bit\b|cloud|"
                     r"programm|python|java|react|angular|\.net", re.I)


def parse_keejob(text):
    rows = []
    for line in text.splitlines():
        m = KJ_LINE.match(line.strip())
        if not m: continue
        title, base, id_, rest = m.groups()
        title = re.sub(r"\\(.)", r"\1", title)
        parts = [p.strip() for p in rest.split(" · ")]
        posted = None
        if parts and parts[-1].startswith("publiée le "):
            posted = to_iso(parts.pop()[len("publiée le "):] + "T00:00:00+00:00")
        company = parts[0] if parts else ""
        location = parts[1] if len(parts) > 1 else "Tunisie"
        extra = parts[2:]
        mode = next((p for p in extra if p.lower() in KJ_MODES), "")
        contract = ", ".join(p for p in extra if p.lower() not in KJ_MODES)
        rows.append({"id": id_, "title": title, "company": company, "location": location, "contract": contract,
                     "mode": mode, "posted": posted, "md": base + ".md", "url": base + "/"})
    return rows


def f_keejob(max_details=30):
    rows = parse_keejob(http_text("https://www.keejob.com/llms-full.txt"))
    tech = [r for r in rows if KJ_TECH.search(r["title"])]
    out, fetched = [], 0
    for r in tech:
        desc = ""
        if fetched < max_details:
            try:
                time.sleep(1.5); desc = http_text(r["md"]); fetched += 1
            except urllib.error.HTTPError as e:
                if e.code in (403, 429): fetched = max_details  # asked to slow down: stop fetching details
            except Exception:
                pass
        extra = f"Contrat: {r['contract']}. " if r["contract"] else ""
        out.append(job("keejob", r["id"], r["title"], r["company"], r["location"],
                       extra + (f"Mode: {r['mode']}. " if r["mode"] else "") + desc, r["url"], r["posted"],
                       remote=r["mode"].lower() in ("télétravail", "teletravail")))
    return out

# ---------------- scoring ----------------
def has(text, term):
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def region(j):
    loc = (j["location"] + " " + j["title"]).lower()
    for name in ("tunisia", "khalij", "europe"):
        if any(has(loc, t) for t in CFG["locations"][name]): return name
    return "remote" if j["remote"] or any(has(loc, t) for t in CFG["locations"]["remote"]) else "other"


def score(j):
    P, W = CFG["profile"], CFG["weights"]
    title, text = j["title"].lower(), (j["title"] + " " + j["description"]).lower()
    reasons, s = [], 0
    if any(has(title, t) for t in P["titles"]): s += W["title_match"]; reasons.append("title")
    sk = sorted({k: v for k, v in P["skills"].items() if has(text, k)}.items(), key=lambda kv: -kv[1])
    s += min(W["skill_cap"], sum(v * 4 for _, v in sk))
    if sk: reasons.append("skills: " + ", ".join(k for k, _ in sk[:6]))
    if any(has(text, t) for t in P["junior_terms"]): s += W["junior_boost"]; reasons.append("junior-friendly")
    if any(has(title, t) for t in P["senior_terms"]) or re.search(r"\b([3-9]|1\d)\+? ?(years|ans|yrs)", text):
        s -= W["senior_penalty"]; reasons.append("seniority mismatch")
    if any(has(text, t) for t in P["visa_terms"]): s += W["visa_boost"]; reasons.append("visa/relocation")
    reg = region(j)
    if reg in ("tunisia", "europe", "khalij"): s += W["location_match"]
    elif reg == "remote": s += W["remote_boost"]
    blocked = [t for t in P["blocking_language_terms"] if has(text, t)]
    return max(0, min(100, s)), reasons, reg, blocked

# ---------------- pipeline ----------------
def main(argv):
    fixtures = argv[1] if len(argv) > 1 else None  # path to fixture json for offline tests
    jobs, health = [], {}
    if fixtures:
        jobs = json.load(open(fixtures, encoding="utf-8")); health["fixtures"] = len(jobs)
    else:
        S = CFG["sources"]
        tasks = {"arbeitnow": f_arbeitnow, "jobtech_sweden": f_jobtech, "remotive": f_remotive, "jobicy": f_jobicy,
                 "jooble": lambda: f_jooble(S["jooble"]), "adzuna": lambda: f_adzuna(S["adzuna"]),
                 "keejob": f_keejob}
        for name, fn in tasks.items():
            if not S.get(name): continue
            try:
                got = fn(); jobs += got; health[name] = f"ok ({len(got)})"
            except Exception as e:  # one dead source must not kill the run
                health[name] = f"FAILED: {type(e).__name__}: {e}"
    cutoff = datetime.now(timezone.utc) - timedelta(days=CFG["max_age_days"])
    prev_path = os.path.join(ROOT, "data", "jobs.json")
    prev = {}
    if os.path.exists(prev_path):
        prev = {x["id"]: x for x in json.load(open(prev_path, encoding="utf-8")).get("jobs", [])}
    seen, kept = set(), []
    now = datetime.now(timezone.utc).isoformat()
    for j in jobs:
        if j.get("posted") and datetime.fromisoformat(j["posted"]) < cutoff: continue
        key = hashlib.sha1(f"{j['title']}|{j['company']}|{j['location']}".lower().encode()).hexdigest()[:16]
        if key in seen: continue
        seen.add(key)
        sc, why, reg, blocked = score(j)
        if blocked or sc < CFG["min_score"]: continue
        j.update(id=key, score=sc, why=why, region=reg, first_seen=prev.get(key, {}).get("first_seen", now))
        kept.append(j)
    kept.sort(key=lambda x: (-x["score"], x.get("posted") or ""), reverse=False)
    out = {"generated": now, "health": health, "total_fetched": len(jobs), "jobs": kept}
    json.dump(out, open(prev_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    copy = os.path.join(ROOT, "site", "jobs.json")
    json.dump(out, open(copy, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"fetched={len(jobs)} kept={len(kept)}"); [print(f"  {k}: {v}") for k, v in health.items()]
    if all(str(v).startswith("FAILED") for v in health.values()): sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
