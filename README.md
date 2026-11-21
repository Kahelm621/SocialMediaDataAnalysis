# Creator analytics dashboard

A small, auto-refreshing dashboard for Kristi's public posts: YouTube (**KhaosAyngel** and **Strange Biology Club**), X (**@AyngelBytes**), and TikTok when that account exists.

It saves a snapshot every run, draws the history, watches a list of keywords, and writes plain "what to do better" cards that show the numbers they used.

You can open the page with **no API keys**. That view is labeled **DEMO DATA** and is not your real stats. When a key is added, the next run replaces the whole page with live snapshots. Demo rows are never copied into the live files.

## What was already in this repo

Kept, and called out where the behavior changed:

- `notebooks/analysis.ipynb` was a template. It loaded a missing file, `data/your_data.csv`, and a placeholder column named `column_name`, so it could not run. It now loads `data/exports/engagement.csv`, which the dashboard build writes from the same snapshots (or from the demo set). The notebook still does the original kind of pass: shape of the data, missing values, duplicates, an outlier screen, a histogram, a correlation heatmap, and engagement by category.
- `data/twitter_data.csv` is not a spreadsheet. It is an older Python sentiment script that was saved with a `.csv` name. It is untouched. The dashboard does not read it.
- `Refresh` is a one-line note (`gh auth refresh ...`) from an earlier GitHub login. It is not the data refresh. The refresh that collects posts is `python scripts/refresh.py` and `.github/workflows/refresh.yml`.
- `requirements.txt` still installs pandas, numpy, matplotlib, and seaborn for the notebook. Requests, PyYAML, and pytest were added for collection, config, and tests.

## Try it in five minutes (no keys)

From the repo folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/refresh.py
```

Open `dashboard/index.html` in a browser. Charts load Plotly from the internet. The tables work even if the charts cannot load.

You should see a yellow **DEMO DATA** banner. The sample story is intentional: KhaosAyngel titles run long, 18:00 UTC posts do better than 03:00 UTC posts in the sample, and "balatro" / "guess the game" rise while "steam" falls. Strange Biology Club's sample titles are already about as long as the sample top videos.

Rebuild the page any time with:

```bash
python scripts/build_dashboard.py
```

Regenerate the sample files (this does not touch live snapshots) with:

```bash
python scripts/make_demo.py
```

## How to read the page

Use the filters for platform, account, date, and keyword. They work on a phone.

- **Performance** is your own accounts. Followers over time, then one line per post. The metric menu switches among views, likes, comments, shares, engagement rate, and views per day.
- **Trends** is other people's top videos and hashtag attention for the phrases in `config/tracked.yaml`. With "All platforms" selected, the keyword chart stays on YouTube so different kinds of counts are not drawn on one axis. Pick X or TikTok to switch.
- **What to do better** compares your titles with those top videos, names a posting hour when the history is wide enough, and lists rising or falling keywords. Each card says which numbers it used. Pick one account to see that account's version.

On X, "views" are impressions. YouTube's public API does not include shares, so those cells stay blank. Thumbnail click-through rate and average view percentage stay blank until you add the optional YouTube Analytics secrets. The demo does not invent those private numbers.

## Edit accounts, keywords, and timezone

Open `config/tracked.yaml`.

- **timezone** is `UTC` until you change it. The posting-hour card uses this clock. Examples: `America/New_York`, `America/Chicago`, `America/Los_Angeles`.
- **YouTube handle** is the @name, without the @. A display name with spaces is often not the handle. If a run says the channel was not found, open the channel, copy the channel id (it starts with `UC`), and paste it into `channel_id`.
- **Strange Biology Club** is set to handle `StrangeBiologyClub` as a starting guess. Change it if collection cannot find the channel.
- **TikTok** is `enabled: false` until the account exists. Set `handle` (without @) and `enabled: true` when you are ready. The official API still only reads the account that approved your app.
- **keywords** are the phrases to watch. `balatro` is a stand-in game name. Swap in whatever you are playing. `hashtag` is used for X and, if approved, TikTok. If you leave it off, spaces are removed: `guess the game` becomes `guessthegame`.

Save the file. The next refresh uses it. Keyword changes do not rewrite old snapshots.

## Step by step: YouTube API key

This unlocks public subscribers, views, likes, comments, and keyword search for both channels. It does not include watch time or click-through rate.

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (any name is fine).
3. Go to **APIs & Services → Library**, search for **YouTube Data API v3**, and enable it.
4. Go to **APIs & Services → Credentials → Create credentials → API key**.
5. Edit the key and restrict it to **YouTube Data API v3**.
6. For a local run, copy `.env.example` to `.env` and set `YOUTUBE_API_KEY`. `.env` is gitignored.
7. For the scheduled run, add a repository secret named exactly `YOUTUBE_API_KEY` (see the secrets section below).

YouTube search costs more quota than a simple channel lookup. The limits in `config/tracked.yaml` keep each run small. A default quota of 10,000 units per day is enough for a run every 6 hours at these limits.

## Step by step: X bearer token

This unlocks public metrics for **@AyngelBytes** (likes, replies, reposts, quotes, impressions, followers) and recent hashtag counts.

1. Open [the X developer portal](https://developer.x.com/).
2. Create a project and an app.
3. Open the app's **Keys and tokens** and generate a **Bearer Token**.
4. Put it in `.env` as `X_BEARER_TOKEN`, and add the same name as a repository secret.

The recent-counts endpoint needs access that some free apps do not have. If X returns "forbidden", the collector saves a small recent sample instead and the page says so. That sample is not the real volume of the hashtag.

## TikTok (optional, official APIs only)

Nothing in this project scrapes TikTok. There is no unofficial fallback.

Two different approvals exist:

| What you want | API | Secret | What it unlocks |
| --- | --- | --- | --- |
| Your own videos and follower count | Display API (Login Kit) | `TIKTOK_ACCESS_TOKEN` | Stats for the account that approved the app. It cannot look up a random public handle. |
| Hashtag volume | Research API | `TIKTOK_RESEARCH_TOKEN` | A sample of public videos for each hashtag, after TikTok approves a research application. |

Setup sketch:

1. Open [TikTok for Developers](https://developers.tiktok.com/).
2. Create an app. For your own videos, add **Login Kit** and the video list product, complete review, and copy the user access token into `TIKTOK_ACCESS_TOKEN`.
3. In `config/tracked.yaml`, set the TikTok handle and `enabled: true`.
4. For hashtags, apply for the **Research API** separately. If it is approved, put the client access token in `TIKTOK_RESEARCH_TOKEN`.

Until those exist, TikTok stays in the source list as skipped. The demo page includes a sample TikTok account so you can see the layout. That sample disappears as soon as any real snapshot exists, instead of sitting next to live YouTube numbers.

## YouTube Analytics (optional, private metrics)

Public view and like counts work with the API key alone. Click-through rate (thumbnail CTR) and average view percentage need OAuth.

1. In the same Google Cloud project, enable **YouTube Analytics API**.
2. Create an OAuth client of type **Web application**.
3. Add `https://developers.google.com/oauthplayground` as an authorized redirect URI.
4. Open the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/).
5. Click the gear icon and turn on **Use your own OAuth credentials**. Paste the client id and secret.
6. In the scope box, enter `https://www.googleapis.com/auth/yt-analytics.readonly`. Authorize with the Google account that owns the channel.
7. Exchange the code for tokens and copy the **refresh token**.
8. Save three secrets: `YOUTUBE_OAUTH_CLIENT_ID`, `YOUTUBE_OAUTH_CLIENT_SECRET`, `YOUTUBE_ANALYTICS_REFRESH_TOKEN`.

You still need `YOUTUBE_API_KEY`. Analytics is attached after the public channel lookup. Repeat the playground step for the other channel if Google only grants one channel per consent. A run that cannot fetch Analytics still saves the public stats.

## Repository secrets

GitHub → **Settings → Secrets and variables → Actions → New repository secret**.

The name must match. An empty secret is not required. Leave it unset and that source is skipped.

| Secret | Required? | What it unlocks |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | For live YouTube | Your channel stats, watchlist search, the most-popular charts, competitor channels you enable, and the outlier sample. |
| `X_BEARER_TOKEN` | For live X | @AyngelBytes public metrics, plus recent hashtag counts (or a labeled sample if X refuses the counts endpoint). |
| `TIKTOK_ACCESS_TOKEN` | Optional | Your own TikTok videos and follower count, only for the account that approved the app. |
| `TIKTOK_RESEARCH_TOKEN` | Optional | Hashtag samples from the TikTok Research API after approval. |
| `YOUTUBE_OAUTH_CLIENT_ID` | Optional | OAuth client for YouTube Analytics. Does nothing alone. |
| `YOUTUBE_OAUTH_CLIENT_SECRET` | Optional | OAuth client secret for YouTube Analytics. |
| `YOUTUBE_ANALYTICS_REFRESH_TOKEN` | Optional | Thumbnail CTR and average view percentage for the last 28 days. |

Local runs use the same names in `.env`. A value already set in the environment wins over `.env`.

## Turn on GitHub Pages

The site is the `dashboard/` folder. The refresh workflow uploads it to Pages.

1. GitHub → **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Open the **Actions** tab → **Refresh creator analytics** → **Run workflow**.

The first run with no secrets does not commit anything if `dashboard/` is already built. It still deploys that demo page. After a secret is added, the next run appends snapshots, rebuilds the page from **live data only**, commits, and deploys.

The address looks like `https://<user>.github.io/SocialMediaDataAnalysis/`.

If the commit step fails, branch protection is probably blocking the Actions bot from pushing to the default branch. Allow GitHub Actions to write to that branch, or the snapshots will not accumulate. The Actions log prints each source as `ok`, `skipped`, or `error`.

## Schedule

`.github/workflows/refresh.yml` runs every 6 hours and whenever you press **Run workflow**. Each success with a key appends a timestamped snapshot. Old lines stay in git so the charts can show change. Do not delete old lines in `data/snapshots/` if you want that history.

Tests run on `.github/workflows/tests.yml` for every push and pull request. They do not need secrets.

## YouTube as a whole

The page has two views. **My channels** is your accounts, your SEO checklist, competitors you turn on, and content ideas. **YouTube explorer** is the public most-popular charts, title patterns, a keyword estimate, and outliers.

The scheduled collector is built for the free YouTube Data API cap of **10,000 units per day**. `search.list` costs 100 units. `videos.list`, `channels.list`, `playlistItems.list`, and `videoCategories.list` cost 1. The workflow runs every 6 hours, so that is 4 runs a day. With the default `config/tracked.yaml` the plan is about **670 units per day**, and the collector stops itself at 8,000 so a long watchlist cannot spend the whole cap.

What each run spends:

- Most-popular chart for US, GB, CA, and AU, plus category charts for the US only (Gaming, Science & Technology, Education, and the other categories in the config). Category charts are not repeated for every region.
- Your two channels, and any competitor with `enabled: true` plus a handle or channel id.
- Watchlist search **once per day** (the midnight run, UTC). Pressing **Run workflow** forces a search. So does `python scripts/refresh.py --search`.
- Recent uploads for up to 8 channels that appeared on that run's trending chart, so the outlier check has a channel median to compare. That is a sample, not all of YouTube.
- Autocomplete suggestions. Those use Google's public suggest endpoint, cost 0 Data API units, and are not search volume.

Look up a phrase that is not on the watchlist without waiting for the schedule:

```bash
python scripts/research_keyword.py "guess the game"
python scripts/research_keyword.py "hades" --save
```

`--save` appends a real snapshot. Each lookup is about 102 units.

Read any public video's title, description, tags, and the same SEO checklist the page uses (1 unit):

```bash
python scripts/analyze_video.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Add a competitor in `config/tracked.yaml` under `competitors:`. Set `enabled: true` and paste the @handle or the channel id. Leave the examples disabled until you do.

### What is included, and what YouTube will not give us

Included, and labeled as an estimate when it is one:

- Trending / most-popular videos by region and category, how many snapshots they stay on the chart, Shorts vs longer videos (60 seconds or less), and title patterns (length, numbers, caps, emoji, question marks).
- Wording that is showing up more often in trending titles and tags, and which channels have the most videos on that chart.
- A keyword opportunity score from the top search results: median views, median subscribers, and how many results are already large. The formula is printed on the page.
- Outlier videos at least 3× the median of that channel's videos in the snapshot.
- SEO score for your videos (title, description, tags, chapters, hashtags) with a fix for each miss.
- Best posting hour from your history. Trending publish times are not treated as your best hour.
- Content ideas built only from those rising phrases, outliers, and trending words.
- Hashtag counts for X, and for TikTok if the Research API token exists.
- Optional channel CTR and average view percentage when the Analytics secrets are set.

Not in this version, because the API does not provide them or they would blow the quota:

- True YouTube search volume. `totalResults` is only a rough cap, and the page does not pretend otherwise.
- A live views-per-hour counter like a browser extension. You get lifetime pace (views ÷ hours since publish) and snapshot pace (change between the last two saves).
- Whether a thumbnail was designed by you. The API only shows that an image exists.
- Per-video traffic sources and retention curves. The optional Analytics call saves channel-level CTR and average view percentage for the last 28 days.
- Every video on YouTube. Outliers come from your videos, competitors you enable, and a handful of channels on the trending chart.

## How the math works

- **Engagement rate** = (likes + comments + shares) / views. Missing shares are left out. No views means no rate, instead of dividing by zero.
- **Views per day** = (views now − views last snapshot) / days between those two snapshots. One snapshot is not enough, so the first point has no pace.
- **YouTube keyword attention** = combined views of the top search results in the lookback window (30 days by default). YouTube does not publish an exact count of videos for a phrase.
- **Opportunity** = demand × (100 − competition) / 100. Demand is a 0–100 log score of median views on those results (100 means about 1,000,000 views), with a quarter of the blend from how many autocomplete suggestions came back. Competition is half the log score of those channels' median subscribers and half the share of results at or above 100,000 views (change that line in `youtube_quota.strong_view_threshold`).
- **Lifetime pace** = views ÷ hours since publish. **Snapshot pace** = view change between the last two saves ÷ hours between them.
- **SEO score** is points out of 100 for title length (40–70 characters), keyword in the first 40 characters, a description opening, tags, chapters, and hashtags. Each missed check has its own fix sentence.
- **Outlier** = views at least `outlier_multiplier` (default 3) times the median of that channel's videos in the latest snapshot.
- **Rising / falling** compares the latest attention number with the snapshot from about seven days earlier. If the history is shorter than a week, it uses the previous snapshot. The default line is +15% and −15%, set in `config/tracked.yaml`. Six hours is too short a gap for most phrases to move that far, which is why the comparison looks back about a week.
- **Title length, keyword placement, and numbers** compare your YouTube and TikTok titles with the latest top videos for your keywords. A tracked phrase "in front" means it appears in the first 40 characters. X captions are not treated as titles.
- **Best posting hour** uses the publish time in your configured timezone and the median engagement rate. It stays quiet until there are enough posts in at least two different hours.

## Tests

```bash
pytest
```

The tests cover engagement rate, views per day, rising and falling keywords, title patterns, the suggestion cards, the rule that demo rows cannot be written into `data/snapshots`, collectors against fake API responses (including secret redaction), and a dashboard build that stays on demo data until a real snapshot exists.

## Project layout

```text
config/tracked.yaml          accounts, keywords, timezone
src/creator_analytics/       collection, math, suggestions, page build
scripts/refresh.py           collect (skip missing keys) and rebuild
scripts/build_dashboard.py   rebuild the page only
scripts/make_demo.py         rewrite data/demo
data/demo/                   labeled sample history
data/snapshots/              live history, committed by Actions
data/exports/engagement.csv  one row per post, for the notebook
dashboard/index.html         the page GitHub Pages serves
notebooks/analysis.ipynb     the original notebook, now pointed at the export
.github/workflows/           tests, and the 6-hour refresh
```

## Privacy

Only public numbers are collected, unless you add the optional YouTube Analytics OAuth. Tokens stay in `.env` or in GitHub Actions secrets. They are not written into snapshots, and error messages have secrets stripped out.
