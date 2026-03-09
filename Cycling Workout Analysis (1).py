"""
history.py
Manages the training log — saves and loads session summaries as JSON.
Each session is stored as a lightweight summary dict (no raw time series).
"""

import json
import os
import datetime
from pathlib import Path
from fit_parser import SessionData
from analytics import RideAnalytics


HISTORY_FILE = Path("training_history.json")


def _session_to_record(sd: SessionData, ra: RideAnalytics,
                        filename: str, coach_notes: str = "") -> dict:
    return {
        "filename":     filename,
        "date":         sd.start_datetime.isoformat() if sd.start_datetime else None,
        "duration_min": round(sd.duration_s / 60, 1),
        "distance_km":  round(sd.distance_m / 1000, 2),
        "elevation_m":  sd.total_ascent_m,
        "calories":     sd.calories,
        "avg_hr":       round(ra.avg_hr, 1),
        "max_hr":       ra.max_hr,
        "avg_power":    round(ra.avg_power, 1),
        "np":           round(ra.np, 1),
        "max_power":    sd.max_power,
        "vi":           round(ra.vi, 3),
        "if_val":       round(ra.if_val, 2),
        "tss":          round(ra.tss, 1),
        "avg_wkg":      round(ra.avg_wkg, 2),
        "np_wkg":       round(ra.np_wkg, 2),
        "best_5min_w":  round(ra.best_5min, 1),
        "best_20min_w": round(ra.best_20min, 1),
        "best_20min_wkg": round(ra.best_20min / ra.weight_kg, 2) if ra.weight_kg else 0,
        "avg_cadence":  round(ra.avg_cadence, 1),
        "cardiac_drift":ra.cardiac_drift_pct,
        "power_fade":   ra.power_fade_pct,
        "coach_notes":  coach_notes,
        "weight_kg":    ra.weight_kg,
        "ftp":          ra.ftp,
        "saved_at":     datetime.datetime.now().isoformat(),
    }


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_session(sd: SessionData, ra: RideAnalytics,
                 filename: str, coach_notes: str = "") -> None:
    history = load_history()
    record = _session_to_record(sd, ra, filename, coach_notes)

    # Deduplicate by filename + date
    history = [h for h in history
               if not (h.get("filename") == filename
                       and h.get("date") == record["date"])]
    history.append(record)

    # Keep most recent 100 sessions
    history = sorted(history, key=lambda x: x.get("date") or "", reverse=True)[:100]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def delete_session(index: int) -> None:
    history = load_history()
    if 0 <= index < len(history):
        history.pop(index)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
