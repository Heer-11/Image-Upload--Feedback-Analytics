"""
generate_daily_data.py

Generates / extends a dummy dataset of user feedback on the "Image Upload"
feature of a Copilot-style product, for the Image Upload Feedback Analytics
dashboard.

Why it's built this way:
- Idempotent: running it twice on the same day does not duplicate that day.
- Rolling window: keeps the last ROLLING_WINDOW_DAYS days of data so the
  dataset (and the repo history) doesn't grow forever.
- Deterministic-ish randomness seeded by date, so re-running for a date
  you've already generated reproduces the same numbers (useful for demos
  and for making Action diffs sensible).
- Writes both JSON (consumed directly by the dashboard) and CSV (for
  SQL/Excel-style analysis, which is what the sql/analysis_queries.sql
  file in this repo assumes).

Run manually:
    python data/generate_daily_data.py

Run for a specific "as of" date (useful for testing):
    python data/generate_daily_data.py --as-of 2026-09-20

This script is also what the GitHub Action (.github/workflows/update-data.yml)
runs on a daily schedule, then commits the changed data files. That's the
"automation" piece: new day of feedback appears -> files change -> Pages
redeploys -> dashboard shows the new day next time it's opened.
"""

import argparse
import csv
import json
import random
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROLLING_WINDOW_DAYS = 120
DATA_DIR = Path(__file__).parent
JSON_PATH = DATA_DIR / "feedback_data.json"
CSV_PATH = DATA_DIR / "feedback_data.csv"

CATEGORIES = [
    "Blurry / low-res detection",
    "False positive object tag",
    "Missed object in image",
    "Wrong label applied",
    "Duplicate upload not caught",
    "Slow processing time",
    "Upload failed / crashed",
    "Correct result, great experience",
]

# Rough weight of how often each category is the *reason* behind a
# feedback event, and whether that category tends to read positive/negative.
CATEGORY_PROFILE = {
    "Blurry / low-res detection":       {"weight": 12, "negative_bias": 0.75},
    "False positive object tag":        {"weight": 14, "negative_bias": 0.80},
    "Missed object in image":           {"weight": 16, "negative_bias": 0.85},
    "Wrong label applied":              {"weight": 13, "negative_bias": 0.78},
    "Duplicate upload not caught":      {"weight": 7,  "negative_bias": 0.60},
    "Slow processing time":             {"weight": 9,  "negative_bias": 0.55},
    "Upload failed / crashed":          {"weight": 6,  "negative_bias": 0.90},
    "Correct result, great experience": {"weight": 23, "negative_bias": 0.03},
}

REGIONS = ["NA", "EU", "APAC", "LATAM"]


@dataclass
class DayRecord:
    date: str
    total_feedback: int
    positive: int
    negative: int
    neutral: int
    avg_recognition_accuracy: float  # 0-100, model quality proxy for the day
    avg_resolution_time_hours: float
    uploads_processed: int
    category_breakdown: dict
    region_breakdown: dict


def _rng_for_date(d: date) -> random.Random:
    # Seed off the date so the same day always regenerates identically.
    seed = int(d.strftime("%Y%m%d"))
    return random.Random(seed)


def build_day(d: date) -> DayRecord:
    rng = _rng_for_date(d)

    # Simulate weekday vs weekend upload volume, plus mild upward trend
    # over the window so the dashboard has something to tell a "story" with.
    day_index = (d - (date.today() - timedelta(days=ROLLING_WINDOW_DAYS))).days
    weekday_factor = 0.65 if d.weekday() >= 5 else 1.0
    base_volume = 1400 + day_index * 3
    uploads_processed = max(200, int(rng.gauss(base_volume, 120) * weekday_factor))

    # Not every upload generates explicit feedback.
    total_feedback = max(20, int(uploads_processed * rng.uniform(0.06, 0.11)))

    # Pick category counts using weighted profile.
    weights = [CATEGORY_PROFILE[c]["weight"] for c in CATEGORIES]
    picks = rng.choices(CATEGORIES, weights=weights, k=total_feedback)
    category_breakdown = {c: picks.count(c) for c in CATEGORIES}

    positive = negative = neutral = 0
    for cat, count in category_breakdown.items():
        neg_bias = CATEGORY_PROFILE[cat]["negative_bias"]
        for _ in range(count):
            r = rng.random()
            if r < neg_bias:
                negative += 1
            elif r < neg_bias + 0.10:
                neutral += 1
            else:
                positive += 1

    # Model quality proxy: trends slightly upward, with noise, capped 0-100.
    trend_lift = min(6.0, day_index * 0.03)
    avg_recognition_accuracy = round(
        min(99.5, max(70.0, rng.gauss(87 + trend_lift, 2.5))), 2
    )

    avg_resolution_time_hours = round(max(0.5, rng.gauss(6.5, 2.0)), 2)

    region_breakdown = {}
    remaining = total_feedback
    for i, region in enumerate(REGIONS):
        if i == len(REGIONS) - 1:
            region_breakdown[region] = remaining
        else:
            share = int(total_feedback * rng.uniform(0.15, 0.4))
            share = min(share, remaining)
            region_breakdown[region] = share
            remaining -= share

    return DayRecord(
        date=d.isoformat(),
        total_feedback=total_feedback,
        positive=positive,
        negative=negative,
        neutral=neutral,
        avg_recognition_accuracy=avg_recognition_accuracy,
        avg_resolution_time_hours=avg_resolution_time_hours,
        uploads_processed=uploads_processed,
        category_breakdown=category_breakdown,
        region_breakdown=region_breakdown,
    )


def load_existing() -> list:
    if JSON_PATH.exists():
        with open(JSON_PATH, "r") as f:
            payload = json.load(f)
            return payload.get("days", [])
    return []


def save(records: list) -> None:
    records = sorted(records, key=lambda r: r["date"])
    with open(JSON_PATH, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "team": "Copilot Feedback Analytics",
                "surface": "Image Upload",
                "days": records,
            },
            f,
            indent=2,
        )

    # Flat CSV, one row per day, categories/regions flattened for SQL/Excel use.
    fieldnames = [
        "date", "total_feedback", "positive", "negative", "neutral",
        "avg_recognition_accuracy", "avg_resolution_time_hours",
        "uploads_processed",
    ] + [f"cat__{c}" for c in CATEGORIES] + [f"region__{r}" for r in REGIONS]

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {
                "date": r["date"],
                "total_feedback": r["total_feedback"],
                "positive": r["positive"],
                "negative": r["negative"],
                "neutral": r["neutral"],
                "avg_recognition_accuracy": r["avg_recognition_accuracy"],
                "avg_resolution_time_hours": r["avg_resolution_time_hours"],
                "uploads_processed": r["uploads_processed"],
            }
            for c in CATEGORIES:
                row[f"cat__{c}"] = r["category_breakdown"].get(c, 0)
            for reg in REGIONS:
                row[f"region__{reg}"] = r["region_breakdown"].get(reg, 0)
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=str, default=None,
                         help="YYYY-MM-DD to treat as 'today' (for testing).")
    args = parser.parse_args()

    today = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()
    window_start = today - timedelta(days=ROLLING_WINDOW_DAYS - 1)

    existing = {r["date"]: r for r in load_existing()}

    all_days = {}
    d = window_start
    while d <= today:
        key = d.isoformat()
        if key in existing:
            all_days[key] = existing[key]
        else:
            all_days[key] = asdict(build_day(d))
        d += timedelta(days=1)

    save(list(all_days.values()))
    print(f"Wrote {len(all_days)} days of data through {today.isoformat()} "
          f"-> {JSON_PATH.name}, {CSV_PATH.name}")


if __name__ == "__main__":
    main()
