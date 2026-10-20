# job-radar
Daily job discovery for Tunisia, Europe and the Khalij. Free: GitHub Actions + GitHub Pages.

## Setup (10 min)
1. Create a private-or-public GitHub repo, push this folder. (Pages on private repos needs a paid plan; use a public repo — it contains only job listings, no CV.)
2. Settings → Pages → Source: **GitHub Actions**.
3. Optional free API keys → repo Settings → Secrets: `JOOBLE_KEY` (jooble.org/api/about; covers Tunisia + Gulf), `ADZUNA_ID`/`ADZUNA_KEY` (developer.adzuna.com; EU countries). Without them those sources are skipped and shown as FAILED in the dashboard footer; Arbeitnow, JobTech (Sweden), Remotive and Jobicy need no key.
4. Actions → daily-job-radar → Run workflow. Dashboard: `https://<user>.github.io/<repo>/`.

## Tuning
Everything is in `config.json` (skills weights, junior/senior terms, blocked-language terms, min_score, regions).
Statuses (saved/applied/interview…) are stored in your browser (localStorage) per device.
Offline test: `python run.py tests/fixtures.json`.
