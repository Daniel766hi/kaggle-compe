# Kaggle datasets, updated automatically

Automated pipelines that pull free public data every day and publish a new version of each
Kaggle dataset. One GitHub Actions workflow runs them all.

| Dataset | Command name | Source | Updates |
|---|---|---|---|
| [DeFi Daily: TVL, Stablecoins, DEX & Yields](https://www.kaggle.com/datasets/danielaijdkx/defi-daily-tvl-stablecoins-dex-yields) | `defi` | DefiLlama API | daily |
| [Indonesia Air Quality: Hourly PM2.5, 31 Cities](https://www.kaggle.com/datasets/danielaijdkx/indonesia-air-quality-hourly-pm25) | `idn-air-quality` | Open-Meteo (CAMS), CC BY 4.0 | daily |
| [Indonesia Daily Weather: 31 Cities since 2000](https://www.kaggle.com/datasets/danielaijdkx/indonesia-daily-weather-31-cities) | `idn-weather` | Open-Meteo (ERA5), CC BY 4.0 | daily |
| [Rupiah (IDR) Daily Exchange Rates](https://www.kaggle.com/datasets/danielaijdkx/rupiah-idr-daily-exchange-rates) | `idr-fx` | ECB reference rates via Frankfurter | daily |
| [Indonesia Fire Hotspots (NASA FIRMS, daily)](https://www.kaggle.com/datasets/danielaijdkx/indonesia-fire-hotspots-nasa-firms) | `idn-fires` | NASA FIRMS VIIRS active fires (needs the free `FIRMS_MAP_KEY` secret), geoBoundaries | daily |
| [Indonesia Politics Tracker: Events & Cabinet](https://www.kaggle.com/datasets/danielaijdkx/indonesian-political-moves-database-2024-2026) | `idn-politics` | GDELT events, Wikipedia cabinet tables (CC BY-SA) | daily |
| [Movie Metadata: Genre, Crew, Color & Tech Specs](https://www.kaggle.com/datasets/danielaijdkx/movie-metadata-genre-crew-color-tech-specs) | `movies` | Wikidata (CC0) | weekly (Mondays) |

## How it works

```
GitHub Actions (daily 01:23 UTC = 08:23 WIB), one job per dataset
  └─ python -m kaggle_pipeline <dataset>
       1. download the dataset's current Kaggle version
       2. fetch each source table
       3. merge: replace full histories, append daily snapshots, or upsert new date ranges
       4. compute derived tables (daily/monthly summaries)
       5. write dataset-metadata.json (description, file/column docs, sources, update frequency)
       6. upload a new Kaggle version, then update the dataset settings (cover image, docs)
```

Table kinds (see `kaggle_pipeline/schema.py`):
- **history**: the source returns the full series, so the file is rebuilt every run (DeFi, FX).
- **snapshot**: the source only returns today's state, so each run appends a dated snapshot (DeFi panels).
- **incremental**: the source has history but too much to refetch daily, so each run fetches the
  recent window plus older ranges until a request budget is spent (Open-Meteo). History back to
  2000 (weather) or 2022 (air quality) fills in over the first few runs within the free API limits.
- **derived**: computed from the other tables (daily air quality summary, monthly weather, IDR cross rates).

Safety rules:
- Each source is independent. If one fails, its previous file is carried forward unchanged and the
  run is marked red so GitHub emails you. One dataset failing never stops the others.
- A response with suspiciously few rows, or a table smaller than before, is rejected.
- If the previous version can't be downloaded, nothing is uploaded, so history is never erased.
- Re-running on the same day replaces that day's data instead of duplicating it.
- Public/private visibility is kept as you set it on kaggle.com.

## Setup (one time)

1. **Kaggle token**: kaggle.com → *Settings* → *API* → *Generate New Token*.
2. **GitHub**: this repo → *Settings* → *Secrets and variables* → *Actions*:
   - Secret `KAGGLE_API_TOKEN` = the token (or, with a legacy `kaggle.json` key: secret `KAGGLE_KEY`)
   - Variable `KAGGLE_USERNAME` = your Kaggle username
3. **Run**: *Actions* → *Update Kaggle datasets* → *Run workflow*. New datasets are created
   **private**; review them on Kaggle and make them public in the dataset settings.
   A manual run can target one dataset (e.g. `idn-weather`) and can be a **dry run**, which
   builds and logs the files without uploading anything.

GitHub pauses scheduled workflows in **public** repos after 60 days without commits. If that
happens, re-enable the workflow in the Actions tab.

## Run locally

```bash
pip install -r requirements.txt
pytest -q                                          # offline tests
python -m kaggle_pipeline idr-fx --dry-run         # fetch into ./build/idr-fx, no upload
export KAGGLE_USERNAME=... KAGGLE_API_TOKEN=...
python -m kaggle_pipeline idr-fx                   # fetch and publish
```

## Example notebooks

`notebooks/` holds one example notebook per dataset, written as readable `.py` files
(jupytext percent format). `scripts/push_notebooks.py` converts them and publishes them to Kaggle,
where they run against the current data. They are pushed private by default; add `--public` once
the dataset they use is public.

| Notebook | What it shows |
|---|---|
| `defi_market_overview.py` | DeFi TVL, stablecoins, DEX volume and yields |
| `rupiah_since_1999.py` | Rupiah crises, trends and volatility |
| `indonesia_air_quality.py` | PM2.5 across 31 cities |
| `indonesia_weather.py` | Rain seasons and warming |
| `indonesia_fires_and_haze.py` | Worst fire years, the fire calendar, provinces, 2026 vs past seasons, fires vs PM2.5 in nearby cities |
| `indonesia_politics_tracker.py` | Protest waves, where protests happen, cabinet reshuffles and unrest before them |
| `movies_oscars_and_recommender.py` | Best Picture nomination/winner prediction (time-based backtest, blind test on the 2026 ceremony, forecast for 2026 films) and an explainable content-based movie recommender |

## Adding a dataset

Create `kaggle_pipeline/datasets/<name>.py` with a `SPEC = DatasetSpec(...)` (tables, fetchers,
description, cover image), register it in `kaggle_pipeline/datasets/__init__.py`, test it with a
manual dry run, then add its name to the scheduled list in the workflow's `matrix.dataset`.
Tags must be Kaggle tags (see `KNOWN_KAGGLE_TAGS`, at most 5). Cover images are drawn from real data with
`scripts/make_cover.py` (needs `pip install matplotlib`).

## Licences and attribution

Each dataset's description credits its source. DeFi data is from DefiLlama's free API (licence
"Other"); Open-Meteo data is CC BY 4.0 (with Copernicus/ECMWF attribution); ECB reference rates
may be reused with the source acknowledged.

## X (Twitter) agent

`x_agent/` is an AI agent for an X account. Claude (Anthropic API) searches the web for recent
news, comes up with post ideas from the content pillars in `x_agent/profile.md`, and writes each one
as a ready-to-publish post or thread. Drafts wait in `content/x_queue.json` until you approve them.
A scheduled workflow then publishes one approved post per run.

```
python -m x_agent ideas --count 5          # research and draft 5 posts
python -m x_agent list                     # what's waiting
python -m x_agent show 3                   # full text, sources, what to fact-check
python -m x_agent revise 3 "shorter, lead with the number"
python -m x_agent approve 3                # ready to publish
python -m x_agent post --dry-run           # what the next run would post
python -m x_agent autopilot                # what the workflow runs (see below)
```

Guardrails:
- The agent may not invent facts. Statistics need a source URL found by web search. Claims about
  you must be in `profile.md`. Anything you should verify is listed under "Check before approving".
- Nothing is posted without approval unless you turn on `X_AUTO_APPROVE`. Even then, drafts
  that need a fact check always wait for you.
- Posts over the length limit are never sent (280 characters; set `X_MAX_CHARS` for X Premium).
- At most one post or thread per run. A thread that fails part way records what went out, so it
  isn't posted twice.

Setup:
1. Edit `x_agent/profile.md`: who you are, goals, content pillars and voice.
2. Get an Anthropic API key (console.anthropic.com) and X API keys: developer.x.com → your app →
   *User authentication settings*: **Read and write** → *Keys and tokens*: API key and secret, plus
   an access token and secret generated **after** setting write permission.
3. Local use: `pip install -r requirements.txt`, export `ANTHROPIC_API_KEY`, `X_API_KEY`,
   `X_API_SECRET`, `X_ACCESS_TOKEN` and `X_ACCESS_TOKEN_SECRET`.
4. Automation: add the same five values as repo **secrets**, then the repo **variable**
   `X_AGENT_ENABLED=true`. The *X agent* workflow runs at 07:17 and 18:47 WIB. Each run creates
   new drafts when fewer than 5 are waiting, posts the oldest approved one, and commits the queue.
   From the Actions tab you can also run any command, e.g. `approve 3 4` or `ideas --theme "rupiah"`.
   Optional variables: `X_AUTO_APPROVE=true` (full autopilot), `X_MAX_CHARS`.

This repo is public, so drafts in `content/x_queue.json` are visible on GitHub before they are
posted. Make the repo private if you don't want that.

## TikTok content creator (Higgsfield)

`tiktok_agent/` makes short vertical videos for the channel described in `shorts/profile.md`: by
default, funny and ridiculous AI animal sketches (setup, escalation, punchline). Edit that file to
change the channel; `TIKTOK_PROFILE` / `INSTAGRAM_PROFILE` can point a platform to its own file.
1. **Plan:** Claude plans each video as a three-beat sketch: a hook, 3 shots (an image prompt,
   a motion prompt and on-screen text for each), a voiceover script and a caption.
2. **Approve:** you check the plan. Nothing is rendered before approval, because Higgsfield
   charges credits for every generation.
3. **Render:** Higgsfield makes an image for each shot (Seedream 4), animates it (Kling 3.0 Turbo,
   5 s), and ffmpeg joins the clips into a silent 1080x1920 mp4 (15 s by default).
4. **Inbox:** the video is uploaded to your TikTok inbox as a draft. In the app, add a sound or
   voiceover and the on-screen text, turn on the AI-generated content label, paste the caption and
   post.

```
python -m tiktok_agent ideas --count 3
python -m tiktok_agent show 2
python -m tiktok_agent revise 2 "make the hook about the rupiah record"
python -m tiktok_agent approve 2
python -m tiktok_agent make 2 --no-upload    # preview build/tiktok/2/video.mp4
python -m tiktok_agent make 2                # send to your TikTok inbox
```

Guardrails: the same no-invented-facts rule as the X agent. Image prompts never ask for text,
numbers, logos or real identifiable people. A clip is never generated twice: a failed upload
retries with the clips it already has. At most one video is made per run.

Setup:
1. **Higgsfield:** at cloud.higgsfield.ai, create an API key and secret and buy credits. Set
   `HF_KEY=key:secret`. To use other models, copy their IDs from the model pages into
   `HIGGSFIELD_IMAGE_MODEL` / `HIGGSFIELD_VIDEO_MODEL`. If the video model doesn't allow 5 s
   clips, change `TIKTOK_CLIP_SECONDS`.
2. **TikTok:** at developers.tiktok.com, create an app and add Login Kit and the Content Posting
   API with the `video.upload` scope. Register a redirect URI. Then, once, on your computer:
   ```
   export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=...
   python -m tiktok_agent auth-url --redirect-uri https://your-registered-uri
   # open the link, log in, copy the "code" from the address you land on
   python -m tiktok_agent auth-code CODE --redirect-uri https://your-registered-uri
   ```
   That prints `TIKTOK_REFRESH_TOKEN`, which is valid for about a year. Each run uses it to get
   a fresh access token.
3. **Automation:** add the repo secrets `ANTHROPIC_API_KEY`, `HF_KEY`, `TIKTOK_CLIENT_KEY`,
   `TIKTOK_CLIENT_SECRET` and `TIKTOK_REFRESH_TOKEN`, then the variable
   `TIKTOK_AGENT_ENABLED=true`. The *TikTok agent* workflow runs daily at 09:37 WIB. It plans new
   videos when fewer than 3 are waiting, then makes the oldest approved one and sends it to your
   inbox. Optional variables: `TIKTOK_AUTO_APPROVE=true` (render plans that have nothing to
   fact-check without asking), `TIKTOK_SHOTS`, `TIKTOK_CLIP_SECONDS`.

TikTok only lets apps post directly (without the inbox step) after it audits them. Until then, a
direct post can only be private, so this agent uses the inbox.

## Instagram Reels creator (Higgsfield)

`instagram_agent/` plans and renders videos the same way as the TikTok agent. The difference is
that Instagram's API has **no drafts**: a Reel goes live as soon as it is published. So the agent
finishes each video before uploading it.
- The on-screen text for each shot is burned into the video. Claude keeps it to 12 words or
  fewer, because there is no voiceover.
- An AAC audio track is added: a track from `assets/music/` (royalty-free only, see the README
  there), or silence.
- The caption ends with "Visuals made with AI." unless it already mentions AI.
- Before uploading, the agent checks the Reels requirements: H.264 at 1080x1920, AAC audio,
  3 s to 15 min, at most 300 MB. It also checks that the daily API publishing limit isn't reached.

```
python -m instagram_agent ideas --count 3
python -m instagram_agent show 2
python -m instagram_agent approve 2               # approving means it will be published
python -m instagram_agent make 2 --no-upload      # watch build/instagram/2/video.mp4 first
python -m instagram_agent make 2                  # publish the Reel
python -m instagram_agent quota
```

Setup:
1. **Instagram account:** switch it to a professional account (Creator or Business) and link it
   to a Facebook Page (Instagram → Settings → Accounts Center, or Page settings → Linked accounts).
2. **Meta app:** at developers.facebook.com create an app of type *Business*, add
   *Instagram* (API setup with Facebook login), and note the app ID and secret. You are the app's
   admin, so you can publish to your own account without App Review.
3. **Token, once:** in the Graph API Explorer (developers.facebook.com/tools/explorer), pick your
   app and generate a user token with `instagram_basic`, `instagram_content_publish`,
   `pages_show_list` and `pages_read_engagement`. Then:
   ```
   export META_APP_ID=... META_APP_SECRET=...
   python -m instagram_agent connect <the token from the explorer>
   ```
   This prints `INSTAGRAM_USER_ID` and a Page token that doesn't expire.
4. **Automation:** add the repo secrets `ANTHROPIC_API_KEY`, `HF_KEY`, `INSTAGRAM_USER_ID` and
   `INSTAGRAM_ACCESS_TOKEN`, then the variable `INSTAGRAM_AGENT_ENABLED=true`. The *Instagram
   agent* workflow runs daily at 18:07 WIB. It plans new Reels when fewer than 3 are waiting,
   then publishes the oldest approved one. Optional variables: `INSTAGRAM_AUTO_APPROVE=true`
   (publish plans that have nothing to fact-check without asking: Reels go live with no review
   at all), `INSTAGRAM_SHOTS`, `INSTAGRAM_CLIP_SECONDS`.

The upload uses Meta's resumable upload, which the API offers with Facebook Login. That's why
the account must be linked to a Page, and it's also why the video doesn't need to be hosted
anywhere. If Meta changes the API version, set `INSTAGRAM_GRAPH_VERSION`
(default `v26.0`).

## Run it for free

Everything can run without paying for anything:

| Part | Free option | Paid option (optional) |
|---|---|---|
| The agents' AI | **Ollama**: a local model on your computer (default when `ANTHROPIC_API_KEY` isn't set) | Claude: `ANTHROPIC_API_KEY` |
| Video clips | **Pexels** stock clips, creators credited in the caption (`VIDEO_SOURCE=stock`, the default) | Higgsfield AI clips: `VIDEO_SOURCE=higgsfield` and `HF_KEY` |
| Posting to X | **Open in X**: the office opens X with the post filled in, you press Post, then *I posted it* | X API keys (X charges per post) |
| TikTok, Instagram | Their posting APIs are free | |
| Daily runs | GitHub Actions is free for public repos | |

**One-command setup.** In the repo folder, run the script for your system. It installs what's
missing (Python packages, ffmpeg, Ollama), picks a model that fits your computer's memory and
downloads it, asks for your free Pexels key (and checks that it works), saves your keys in `.env`
(never committed), then opens the office:

| System | First time | After that |
|---|---|---|
| Windows | right-click `setup.ps1` → *Run with PowerShell* | `start-office.ps1` |
| macOS / Linux | `bash setup.sh` | `bash start-office.sh` |

Or set it up by hand:
1. **Ollama:** install it from ollama.com and open it. Then run `ollama pull qwen3:8b` once.
   That's about a 5 GB download and needs 16 GB of RAM. On 8 GB of RAM, use `qwen3:4b` and set
   `OLLAMA_MODEL=qwen3:4b`. Keep the Ollama app running while you use the office.
2. **Pexels:** sign up at pexels.com/api and copy *Your API key*. Set `PEXELS_API_KEY` on your
   computer, and add it as a GitHub secret for the daily video runs.

What changes when it's free:
- **Weaker drafts, no web search.** A local model writes slower and weaker drafts than Claude, and
  it can't search the web, so ideas come from your profile files. Review drafts a little more
  carefully.
- **New drafts come from the office.** Ollama runs on your computer, not on GitHub's servers. The
  daily workflows skip writing new ideas and still publish the videos you approved. Approve in
  the office, then click *Sync with GitHub*.
- **Clips are real stock footage, not AI.** The Reel caption credits the Pexels creators instead
  of saying "made with AI".

## AI Office: chat with your content team

`office/` is a small web app for your own computer. Your content agents sit at desks there, and
you can chat with each of them. They also message you when something needs you.

| Desk | Who | What they do |
|---|---|---|
| 🧭 | **Maya**, Head of Content | Sees every queue, plans, and hands work to the others |
| ✍️ | **Raka**, X writer | Drafts and revises posts from `x_agent/profile.md` |
| 🎬 | **Sari**, TikTok producer | Plans funny animal sketches from `shorts/profile.md` |
| 📸 | **Bima**, Instagram Reels producer | The same, for Reels |

```
pip install -r requirements.txt
ollama pull qwen3:8b                # once; see "Run it for free" below
export PEXELS_API_KEY=...           # free; plus TIKTOK_*, INSTAGRAM_* to publish from the office
python -m office                    # opens http://127.0.0.1:8765
```

- **You chat with them.** Ask "what needs me today?", "draft 3 posts about supply chains" or "make
  #4 funnier". Items appear as cards in the chat.
- **They chat you.** Every 30 minutes (`--checkin-minutes`), and after each job, the producers
  check their queues and message you about anything new: drafts to review, a post that didn't go
  out, a finished video. Unread messages show as badges, a pop-up, and a browser notification
  when the tab is in the background.
- **Only you approve and publish.** The agents can read, draft, revise and reject. Approve,
  *Open in X* / *Post to X now*, *Render preview* and *Publish* are buttons on the cards, and
  they ask for confirmation before anything public happens.
- **Sync with GitHub** pulls what the scheduled runs changed and pushes your approvals and edits to
  `content/`, so the daily workflows use them.

Conversations are saved in `office_data/` (not committed). The server only listens on
127.0.0.1 and refuses requests from other sites, so a web page you visit can't press its buttons.

## Code layout

```
kaggle_pipeline/
  schema.py        Column, Table, DatasetSpec
  frames.py        type conversion and de-duplication shared by all tables
  storage.py       merge with the previous version, write files + metadata
  pipeline.py      builds one version; per-source failure handling; derived tables
  kaggle_sync.py   download current version, create/version on Kaggle, settings update
  http.py          HTTP session with retries
  datasets/
    defi/              DefiLlama (tables, sources, transforms)
    open_meteo.py      cities, request planning and rate-limit budget for Open-Meteo
    idn_air_quality.py
    idn_weather.py
    idr_fx.py
    movies.py          Wikidata movie metadata
    idn_politics.py    GDELT events in Indonesia + cabinet terms from Wikipedia
    idn_fires.py       NASA FIRMS fire detections in Indonesia, by province
x_agent/
  profile.md       who you are, content pillars, voice (the agent writes from this)
  brain.py         Claude: ideas and drafts (web search + JSON schema output), revisions
  queue.py         content/x_queue.json: draft -> approved -> posted
  x_client.py      publish posts and threads with the X API v2
  text.py          post length as X counts it
shorts/            short-video pipeline shared by the TikTok and Instagram agents
  profile.md       the video channel (ridiculous animal sketches); edit to change it
  plans.py         Claude: video plans (shots, on-screen text, voiceover, caption), the video queue
  render.py        Higgsfield image -> clip per shot; ffmpeg joins them, burns in text, adds audio
  cli.py           commands every video agent has (ideas, approve, make, autopilot, ...)
tiktok_agent/
  tiktok.py        TikTok login (OAuth) and upload to your inbox
instagram_agent/
  instagram.py     Instagram Graph API: resumable Reel upload, publish, quota, account setup
llm.py             which AI thinks: a free local model (Ollama) or Claude
local_env.py       keys saved in .env on your computer (setup.ps1 / setup.sh write it)
office/            the AI Office web app (python -m office)
  team.py          the four agents: who they are and their tools
  chat.py          conversations with Claude, check-ins (agents messaging you)
  desks.py         queue work behind each desk; approve/publish only from buttons
  server.py        local web server and JSON API
  static/          the office page
assets/music/      your royalty-free tracks for Reels (optional)
tests/             offline tests with synthetic API payloads
```
