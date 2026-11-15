# HTTP export

BuoyCast can send every finished workout to an HTTP endpoint you run: a
self-hosted training log, an automation tool such as n8n or Home Assistant,
or a small script. You don't need a Strava API subscription for this, and it
can run alongside Strava.

## Setup

Add an `[export]` section to `config.toml` and restart BuoyCast:

```toml
[export]
url = "https://example.com/ingest/buoycast"   # "" = export off
token = "a-long-random-string"                # sent as "Authorization: Bearer <token>"
format = "json"                               # "json" or "fit"
auto_send = true                              # false = only send from workout history
include_hr = true                             # false = strip heart rate before sending
retry_interval_s = 300                        # how often failed sends are retried
timeout_s = 30
```

The token stays on the Pi. The dashboard only shows the endpoint's host name.
Settings → **Workout Export** shows how many workouts have been sent, are
queued, or failed. Each workout in **Workout History** shows its export status
and has a **Send now** / **Send again** button.

## Delivery

- When a workout ends, BuoyCast saves it and then POSTs it.
- If the request fails because of a network error, a timeout, or HTTP 408,
  425, 429 or 5xx, the workout is marked **Retrying**. BuoyCast tries again
  every `retry_interval_s` seconds, and after each new workout, until the
  request succeeds. A workout recorded while the Wi-Fi or your server is
  down still arrives later.
- Any other 4xx status marks the workout **Rejected**. BuoyCast doesn't retry
  it automatically, because sending the same request again would fail the
  same way. Fix the receiver or the token, then use **Send now**.
- Workouts shorter than `[workout] min_workout_distance_m` are not sent
  automatically. You can still send them by hand.
- Workouts recorded before you upgraded to a BuoyCast with export start as
  **Not sent**. Send the ones you want from history.
- Workouts recorded while `url` is empty stay queued and are sent once you
  set one.

Delivery is **at least once**: after a timeout, BuoyCast can't tell whether
your server stored the workout, so it sends it again. **Receivers must
de-duplicate on the workout ID** and treat a repeat as an update, not a new
workout.

Any 2xx response counts as success. BuoyCast ignores the response body.

## Request

```
POST <url>
Authorization: Bearer <token>          (only when token is set)
Content-Type: application/json         (or application/vnd.ant.fit)
Idempotency-Key: <workout id>
X-BuoyCast-Workout-Id: <workout id>
X-BuoyCast-Started-At: <ISO 8601 start time, UTC>
User-Agent: BuoyCast/<version>
```

### `format = "json"`

```json
{
  "schema_version": 1,
  "source": { "app": "buoycast", "version": "0.3.0" },
  "workout": {
    "id": "1520c42233d7",
    "sport": "rowing",
    "sub_sport": "indoor_rowing",
    "started_at": "2026-11-15T02:57:32.928489Z",
    "ended_at": "2026-11-15T03:27:40.112003Z",
    "elapsed_seconds": 1807,
    "total_distance_m": 6120.0,
    "total_strokes": 642,
    "calories": 410,
    "avg_pace_s_per_500m": 147.6,
    "avg_stroke_rate": 21.3,
    "avg_power_watts": 112.4,
    "avg_heart_rate": 141,
    "max_heart_rate": 163
  },
  "samples": [
    {
      "ts": "2026-11-15T02:57:33.088165Z",
      "distance_m": 3.6,
      "stroke_rate": 18.5,
      "power_watts": 124.3,
      "pace_s_per_500m": 138.9,
      "heart_rate_bpm": 98,
      "rr_intervals_ms": [612, 605]
    }
  ]
}
```

| Field | Notes |
|---|---|
| `schema_version` | Goes up only for breaking changes. New fields can appear in any version, so ignore fields you don't know. |
| `workout.id` | Stable for the life of the workout. Use it as the de-duplication key. |
| `started_at`, `ended_at`, `ts` | UTC, ISO 8601. |
| `elapsed_seconds` | Wall-clock time from start to end, including pauses. |
| `total_distance_m` | Metres, from the S4. |
| `total_strokes` | The S4's stroke counter for this workout. |
| `samples` | About one per second while the workout was active. Paused time has no samples. |
| `distance_m` | Cumulative metres at that sample. |
| `stroke_rate` | Strokes per minute. `0` when the monitor reports no rate. |
| `pace_s_per_500m` | Seconds per 500 m. |
| `heart_rate_bpm`, `rr_intervals_ms` | `null` when no strap was connected, or when `include_hr = false`. The summary's `avg_heart_rate` and `max_heart_rate` are also `null` in that case. |

Averages, `power_watts`, `pace_s_per_500m` and the heart-rate fields can be
`null` when the monitor didn't report them. Everything else is always present.

### `format = "fit"`

The body is the same Garmin FIT activity file that BuoyCast uploads to
Strava (`Sport.ROWING` / `SubSport.INDOOR_ROWING`, one record per sample).
The workout ID is only in the headers. Use this format when the receiver
already understands FIT files.

## A minimal receiver

```python
# pip install fastapi uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()
TOKEN = "a-long-random-string"
seen: dict[str, dict] = {}

@app.post("/ingest/buoycast")
async def ingest(request: Request, authorization: str = Header("")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401)
    body = await request.json()
    seen[body["workout"]["id"]] = body   # upsert: repeats replace, not duplicate
    return {"ok": True}
```
