# Football Record Walk

A local web app that graphs football results as cumulative walks: **+1 for a win, −1 for
a loss, flat for a tie**, stepping one position to the right for each game week.

- **Franchises** tab — one line per team, every season from **1920** to today.
- **Quarterbacks → Games** — one line per Hall of Fame (or likely Hall of Fame)
  quarterback, tracking his team's results across his whole career.
- **Quarterbacks → TD** — cumulative passing touchdowns by game.
- **Quarterbacks → INT** — cumulative interceptions by game.
- **Quarterbacks → TD/INT** — cumulative passing touchdowns minus interceptions.
- **NCAAF rivalries** — compare Utah–BYU, Michigan–Ohio State, Alabama–Auburn, or
  Texas–Oklahoma across each program's full history. Modes include all games, regular
  season, bowls, and direct head-to-head meetings. Pre-2001 program points are
  game-by-game from James Howell's historical scores database (seasons it does not cover
  fall back to one season-total step); newer results come from cfbfastR. Each rivalry also
  has an **AP rankings** view plotting both programs' weekly AP Poll position since 1936,
  with #1 at the top of the chart and unranked on the baseline.

Each quarterback metric has **Game-by-game** and **Season timeline** views. Game-by-game
aligns each line at career game one; the season timeline uses a shared 1920-to-present
calendar axis, accumulates each season's contribution from a zero baseline, and shows a
quarterback only during his playing career. QB views can show all games, regular season,
playoffs, or Super Bowls only. Every QB line is solid. The Franchises tab has the same
four modes; Super Bowls steps +1 for a win and −1 for a loss.

Every chart keeps a fixed aspect ratio and zooms like a magnifying glass: scroll or pinch
over the plot to zoom both axes around the cursor, drag to pan, double-click (or `0`) to
reset, and use the minimap to jump around. Notable events — championships, title-game
losses, Hall of Fame QB arrivals, relocations, landmark seasons, and milestones — appear
on the lines as you zoom in, with labels once there is room for them.

- `api/` — FastAPI service that pulls real game results from
  [nflverse/nfldata](https://github.com/nflverse/nfldata) (1999 → present), caches the CSV
  on disk, and serves the cumulative series as JSON.
- `web/` — React + Vite + Recharts front end, served by nginx which proxies `/api`.
- `k8s/` — manifests for Docker Desktop's Kubernetes.

## Run with Docker Compose

```powershell
cd c:\Users\KennyBates\Desktop\support\scripts\nfl
docker compose up --build
```

Open <http://localhost:8080>. The API is also exposed directly on <http://localhost:8000/api/health>.

## Run on Kubernetes (Docker Desktop)

Build the images into the local Docker daemon that Docker Desktop's Kubernetes shares, then apply:

```powershell
cd c:\Users\KennyBates\Desktop\support\scripts\nfl
docker build -t nfl-record-walk-api:local .\api
docker build -t nfl-record-walk-web:local .\web
kubectl apply -f .\k8s\api.yaml
kubectl apply -f .\k8s\web.yaml
kubectl -n nfl rollout status deploy/nfl-web
```

Open <http://localhost:30080>.

Tear down: `kubectl delete namespace nfl`

## Deploy to Render

Render runs the whole app as **one** container: the root [Dockerfile](Dockerfile) builds the
front end and copies it into the API image, which serves it as static files. That keeps it
to a single free instance with no CORS and no second URL.

1. Push this folder to a Git repository.
2. In Render, choose **New → Blueprint** and point it at the repo. It picks up
   [render.yaml](render.yaml).
3. Deploy. The health check is `/api/health`.

Free instances have no persistent disk, so the data caches are written to `/tmp` and are
re-downloaded after a cold start (roughly a minute for the first request to the TD/INT tab).

To try the exact production image locally:

```powershell
docker build -t nfl-record-walk:render .
docker run --rm -p 8090:8000 nfl-record-walk:render
```

## Develop without containers

```powershell
# API
cd api
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GAMES_CACHE_PATH = "$PWD\data\games.csv"
uvicorn app.main:app --reload --port 8000

# Web (separate terminal) — Vite proxies /api to localhost:8000
cd web
npm install
npm run dev
```

## Data sources

| Era | Source | Notes |
| --- | --- | --- |
| 1920&ndash;1998 | FiveThirtyEight Elo dataset, read from the [Internet Archive](https://web.archive.org/web/2023id_/https://projects.fivethirtyeight.com/nfl-api/nfl_elo.csv) | FiveThirtyEight shut down, so the archived snapshot is used. Franchises are already normalised onto modern abbreviations. Starting quarterback names are present from 1950. No week column, so weeks are derived by clustering game dates. |
| 1999&ndash;present | [nflverse/nfldata](https://github.com/nflverse/nfldata) | Still maintained, refreshed every 12 hours. |
| Per-game passing (TD/INT) | [nflverse-data `stats_player_week`](https://github.com/nflverse/nflverse-data/releases/tag/stats_player) | 1999 onwards only. Downloaded once per season and filtered to the tracked quarterbacks. |
| NCAAF history | Published program season, bowl, and rivalry histories | Season W/L/T fallback for seasons without game-level coverage, bowl outcomes, titles, and direct rivalry results. |
| NCAAF historical games | [James Howell's college football scores](https://www.jhowell.net/cf/scores/ScoresIndex.htm) | Game-by-game results for each program through 2000; also cross-checks cfbfastR from 2001 on. |
| NCAAF rankings | Wikipedia per-season rankings articles | Weekly AP Poll positions from 1936 onwards. |
| NCAAF schedules | [cfbfastR-data](https://github.com/sportsdataverse/cfbfastR-data) | Game-level results from 2001 onwards. Pre-2023 bowl omissions are supplemented from published program histories. |

Both files are cached in the `games-cache` volume, so the app works offline after the
first run.

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Liveness check. |
| `GET /api/teams` | Every franchise in the data, including defunct ones, with its span and game count. |
| `GET /api/seasons` | Seasons available in the dataset. |
| `GET /api/records?start_season=&end_season=&game_mode=` | Step labels plus one cumulative value array per team; `game_mode` is `all`, `regular`, `playoffs`, or `superbowls`. |
| `GET /api/quarterbacks` | Curated quarterback roster with resolved career spans. |
| `GET /api/qb-records?ids=&game_mode=` | Career-aligned cumulative walk per quarterback. |
| `GET /api/qb-td-int?ids=&game_mode=&metric=` | Career-aligned cumulative passing TD (`td`), INT (`int`), or TD minus INT (`td_int`). |
| `GET /api/qb-timeline?ids=&game_mode=&metric=` | Season-aligned values across 1920–present; metric is `games`, `td`, `int`, or `td_int`. |
| `GET /api/ncaaf/rivalries` | Available rivalry definitions and display names. |
| `GET /api/ncaaf/teams?rivalry=` | The two programs in a rivalry. |
| `GET /api/ncaaf/seasons?rivalry=` | Available seasons for the selected rivalry. |
| `GET /api/ncaaf/records?rivalry=&start_season=&end_season=&game_mode=` | Cumulative records; mode is `all`, `regular`, `bowl`, or `head_to_head`. |
| `GET /api/ncaaf/rankings?rivalry=&start_season=&end_season=` | Weekly AP Poll position for both programs, 1936&ndash;present. `25` is #1, `1` is #25, `0` is unranked. |
| `GET /api/audit?refresh=` | Data-completeness audit: structural checks plus cross-checks against FiveThirtyEight, nflverse standings/season totals, published career totals, and published NCAAF season/rivalry records. Also shown on the **Data audit** tab. |

Relocated franchises are merged onto their current abbreviation (OAK→LV, SD→LAC, STL→LAR),
so each franchise keeps one continuous line. Defunct franchises (Canton Bulldogs, Frankford
Yellow Jackets, the AAFC clubs, …) are hidden behind a toggle; their games always count
towards their opponents' records regardless.

The quarterback roster lives in [api/app/quarterbacks.py](api/app/quarterbacks.py) — add a
`Quarterback` entry to feature someone new. A stint `end` of `None` means "still active"
and is resolved against the last season the quarterback actually started a game.
