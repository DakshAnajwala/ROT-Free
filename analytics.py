"""
analytics.py
Computes all derived metrics, zone distributions, and builds
the prompt for the AI coach analysis.
"""

import statistics
from dataclasses import dataclass, field
from typing import Optional
from fit_parser import SessionData, best_effort_watts, _calc_np


# ── Zone configuration ────────────────────────────────────────────────────────

DEFAULT_HR_ZONES = {
    "Z1": (100, 120),
    "Z2": (120, 150),
    "Z3": (150, 165),
    "Z4": (165, 185),
    "Z5": (185, 999),
}

ZONE_COLORS = {
    "Z1": "#5c85d6",
    "Z2": "#4caf7d",
    "Z3": "#f0b429",
    "Z4": "#f06529",
    "Z5": "#e8001d",
}

POWER_ZONE_NAMES = {
    1: "Active Recovery",
    2: "Endurance",
    3: "Tempo",
    4: "Threshold",
    5: "VO2max",
    6: "Anaerobic",
}


def power_zones_from_ftp(ftp: float) -> dict:
    return {
        1: (0,         0.55 * ftp),
        2: (0.55*ftp,  0.75 * ftp),
        3: (0.75*ftp,  0.90 * ftp),
        4: (0.90*ftp,  1.05 * ftp),
        5: (1.05*ftp,  1.20 * ftp),
        6: (1.20*ftp,  9999),
    }


# ── Main analytics dataclass ──────────────────────────────────────────────────

@dataclass
class RideAnalytics:
    # Identity
    weight_kg: float = 70.0
    ftp: float = 200.0
    hr_zones: dict = field(default_factory=lambda: dict(DEFAULT_HR_ZONES))

    # Derived power
    avg_power: float = 0
    np: float = 0
    vi: float = 0
    if_val: float = 0
    tss: float = 0
    avg_wkg: float = 0
    np_wkg: float = 0

    # Best efforts (watts & w/kg)
    best_5s:   float = 0
    best_30s:  float = 0
    best_1min: float = 0
    best_5min: float = 0
    best_10min:float = 0
    best_20min:float = 0
    best_60min:float = 0

    # HR stats
    avg_hr: float = 0
    max_hr: int = 0
    hr_zone_pct: dict = field(default_factory=dict)   # {"Z1": pct, ...}
    hr_zone_min: dict = field(default_factory=dict)
    cardiac_drift_pct: float = 0

    # Power zone stats
    pwr_zone_pct: dict = field(default_factory=dict)
    pwr_zone_min: dict = field(default_factory=dict)

    # Cadence
    avg_cadence: float = 0
    max_cadence: int = 0
    cadence_std: float = 0
    early_cadence: float = 0
    late_cadence: float = 0

    # Fatigue
    early_avg_power: float = 0
    late_avg_power: float = 0
    power_fade_pct: float = 0

    # Segments (15-min blocks)
    segments: list = field(default_factory=list)

    # Spikes >400W
    power_spikes: list = field(default_factory=list)


def compute(sd: SessionData, weight_kg: float, ftp: float,
            hr_zones: Optional[dict] = None) -> RideAnalytics:
    """Compute all analytics from a SessionData object."""
    ra = RideAnalytics(weight_kg=weight_kg, ftp=ftp)
    ra.hr_zones = hr_zones or dict(DEFAULT_HR_ZONES)

    pwr = sd.power_ts
    hr  = sd.hr_ts
    cad = sd.cadence_ts
    ts  = sd.timestamps

    valid_pwr = [p for p in pwr if p]
    valid_hr  = [h for h in hr  if h]
    valid_cad = [c for c in cad if c]

    # ── Power metrics ─────────────────────────────────────────────────
    if valid_pwr:
        ra.avg_power = sum(valid_pwr) / len(valid_pwr)
        ra.np        = float(_calc_np(pwr))
        ra.vi        = ra.np / ra.avg_power if ra.avg_power else 0
        ra.if_val    = ra.np / ftp if ftp else 0
        dur_h        = sd.duration_s / 3600
        ra.tss       = (sd.duration_s * ra.np * ra.if_val) / (ftp * 3600) * 100 if ftp else 0
        ra.avg_wkg   = ra.avg_power / weight_kg
        ra.np_wkg    = ra.np / weight_kg

    # ── Best efforts ─────────────────────────────────────────────────
    for dur, attr in [(5, "best_5s"), (30, "best_30s"), (60, "best_1min"),
                      (300, "best_5min"), (600, "best_10min"),
                      (1200, "best_20min"), (3600, "best_60min")]:
        setattr(ra, attr, best_effort_watts(pwr, dur))

    # ── HR metrics ───────────────────────────────────────────────────
    if valid_hr:
        ra.avg_hr = sum(valid_hr) / len(valid_hr)
        ra.max_hr = max(valid_hr)

        # Zone distribution
        zone_counts = {z: 0 for z in ra.hr_zones}
        for h in valid_hr:
            for z, (lo, hi) in ra.hr_zones.items():
                if lo <= h < hi:
                    zone_counts[z] += 1
                    break
        total = sum(zone_counts.values()) or 1
        ra.hr_zone_pct = {z: round(v / total * 100, 1) for z, v in zone_counts.items()}
        ra.hr_zone_min = {z: round(v / 60, 1) for z, v in zone_counts.items()}

        # Cardiac drift
        mid = len(hr) // 2
        h1  = [h for h in hr[:mid]  if h]
        h2  = [h for h in hr[mid:]  if h]
        p1  = [p for p in pwr[:mid] if p]
        p2  = [p for p in pwr[mid:] if p]
        if h1 and h2 and p1 and p2:
            ef1 = (sum(p1)/len(p1)) / (sum(h1)/len(h1))
            ef2 = (sum(p2)/len(p2)) / (sum(h2)/len(h2))
            ra.cardiac_drift_pct = round((ef2 - ef1) / ef1 * 100, 1)

    # ── Power zone distribution ───────────────────────────────────────
    if valid_pwr and ftp:
        pz = power_zones_from_ftp(ftp)
        pz_counts = {z: 0 for z in pz}
        for p in valid_pwr:
            for z, (lo, hi) in pz.items():
                if lo <= p < hi:
                    pz_counts[z] += 1
                    break
        total_p = sum(pz_counts.values()) or 1
        ra.pwr_zone_pct = {z: round(v / total_p * 100, 1) for z, v in pz_counts.items()}
        ra.pwr_zone_min = {z: round(v / 60, 1) for z, v in pz_counts.items()}

    # ── Cadence ───────────────────────────────────────────────────────
    if valid_cad:
        ra.avg_cadence = sum(valid_cad) / len(valid_cad)
        ra.max_cadence = max(valid_cad)
        ra.cadence_std = statistics.stdev(valid_cad) if len(valid_cad) > 1 else 0
        third = len(valid_cad) // 3
        ra.early_cadence = sum(valid_cad[:third]) / third if third else 0
        ra.late_cadence  = sum(valid_cad[2*third:]) / (len(valid_cad) - 2*third) \
                           if 2*third < len(valid_cad) else 0

    # ── Fatigue markers ───────────────────────────────────────────────
    if valid_pwr:
        third = len(pwr) // 3
        ep = [p for p in pwr[:third]     if p]
        lp = [p for p in pwr[2*third:]   if p]
        if ep and lp:
            ra.early_avg_power = sum(ep) / len(ep)
            ra.late_avg_power  = sum(lp) / len(lp)
            ra.power_fade_pct  = round(
                (ra.late_avg_power - ra.early_avg_power) / ra.early_avg_power * 100, 1)

    # ── 15-min segments ───────────────────────────────────────────────
    if ts:
        seg_s = 15 * 60
        total_dur = max(ts)
        n_segs = int(total_dur / seg_s) + 1
        for seg in range(n_segs):
            s0, s1 = seg * seg_s, (seg + 1) * seg_s
            idx = [i for i, t in enumerate(ts) if s0 <= t < s1]
            if not idx:
                continue
            sp = [pwr[i] for i in idx if pwr[i]]
            sh = [hr[i]  for i in idx if hr[i]]
            sc = [cad[i] for i in idx if cad[i]]
            ss = [sd.speed_ts[i] for i in idx if sd.speed_ts[i]]
            ra.segments.append({
                "seg":      seg + 1,
                "start_min": seg * 15,
                "end_min":  (seg + 1) * 15,
                "avg_power": round(sum(sp)/len(sp), 1) if sp else 0,
                "avg_hr":    round(sum(sh)/len(sh), 1) if sh else 0,
                "avg_speed": round(sum(ss)/len(ss), 1) if ss else 0,
                "avg_cad":   round(sum(sc)/len(sc), 1) if sc else 0,
            })

    # ── Power spikes ─────────────────────────────────────────────────
    spike_thresh = max(400, ftp * 1.5) if ftp else 400
    for i, p in enumerate(pwr):
        if p and p > spike_thresh:
            ra.power_spikes.append({
                "time_min": round(ts[i] / 60, 1) if i < len(ts) else 0,
                "watts": p,
            })

    return ra


def build_coach_prompt(sd: SessionData, ra: RideAnalytics) -> str:
    """Build the system + user prompt for the AI coach."""
    dur_min = round(sd.duration_s / 60, 1)
    dist_km = round(sd.distance_m / 1000, 2)
    date_str = sd.start_datetime.strftime("%d %b %Y %H:%M") if sd.start_datetime else "Unknown"
    ftp = ra.ftp
    weight = ra.weight_kg

    hr_zone_summary = ", ".join(
        f"{z}: {ra.hr_zone_pct.get(z, 0):.1f}% ({ra.hr_zone_min.get(z, 0):.0f}min)"
        for z in ra.hr_zones
    )

    pwr_zone_summary = ", ".join(
        f"Z{z} ({POWER_ZONE_NAMES[z]}): {ra.pwr_zone_pct.get(z, 0):.1f}% ({ra.pwr_zone_min.get(z, 0):.0f}min)"
        for z in sorted(ra.pwr_zone_pct.keys())
    ) if ra.pwr_zone_pct else "Not available"

    spikes_summary = f"{len(ra.power_spikes)} readings above {int(max(400, ftp*1.5))}W" \
                     if ra.power_spikes else "None"

    seg_table = "\n".join(
        f"  {s['start_min']}–{s['end_min']}min: {s['avg_power']}W, {s['avg_hr']}bpm, "
        f"{s['avg_speed']}km/h, {s['avg_cad']}rpm"
        for s in ra.segments[:-1]  # exclude cooldown
    )

    prompt = f"""You are an expert cycling coach analysing a real ride file for an amateur cyclist. 
Be direct, specific, and constructive. Use the data below to write a comprehensive performance 
analysis. The rider is NOT a professional — frame feedback as a coach helping an amateur improve. 
Be honest but encouraging. Use concrete numbers from the data.

=== RIDE DATA ===
Date: {date_str}
Duration: {dur_min} min | Distance: {dist_km} km
Elevation: {sd.total_ascent_m}m ascent / {sd.total_descent_m}m descent
Calories: {sd.calories} kcal | Sport: {sd.sport}

Rider profile:
- Weight: {weight}kg
- FTP (set by user): {ftp}W ({ftp/weight:.2f} W/kg)

Power:
- Avg: {ra.avg_power:.0f}W ({ra.avg_wkg:.2f} W/kg)
- Normalized Power (NP): {ra.np:.0f}W ({ra.np_wkg:.2f} W/kg)
- Max: {sd.max_power}W
- Variability Index: {ra.vi:.3f}
- Intensity Factor: {ra.if_val:.2f}
- TSS: {ra.tss:.0f}

Best efforts:
- 5s: {ra.best_5s:.0f}W ({ra.best_5s/weight:.2f} W/kg)
- 30s: {ra.best_30s:.0f}W ({ra.best_30s/weight:.2f} W/kg)
- 1min: {ra.best_1min:.0f}W ({ra.best_1min/weight:.2f} W/kg)
- 5min: {ra.best_5min:.0f}W ({ra.best_5min/weight:.2f} W/kg)
- 20min: {ra.best_20min:.0f}W ({ra.best_20min/weight:.2f} W/kg)
- 60min: {ra.best_60min:.0f}W ({ra.best_60min/weight:.2f} W/kg)

Heart Rate (user HR zones: {', '.join(f"{z}={v[0]}-{v[1]}" for z,v in ra.hr_zones.items())}):
- Avg: {ra.avg_hr:.0f}bpm | Max: {ra.max_hr}bpm
- Zone distribution: {hr_zone_summary}
- Cardiac drift (Pa:HR decoupling): {ra.cardiac_drift_pct:.1f}%

Power zone distribution (based on FTP={ftp}W):
{pwr_zone_summary}

Cadence:
- Avg: {ra.avg_cadence:.0f}rpm | Max: {ra.max_cadence}rpm
- Std dev: {ra.cadence_std:.1f}rpm
- Early (first third): {ra.early_cadence:.0f}rpm → Late (last third): {ra.late_cadence:.0f}rpm

Fatigue markers:
- Early avg power: {ra.early_avg_power:.0f}W → Late avg power: {ra.late_avg_power:.0f}W
- Power fade: {ra.power_fade_pct:.1f}%

Power spikes: {spikes_summary}

15-minute segment breakdown:
{seg_table}

=== ANALYSIS REQUEST ===
Write a structured coaching analysis with these sections:
1. **Session Summary** — What kind of session was this? What was the primary training stimulus?
2. **What Went Well** — 2–3 genuine positives backed by data
3. **Key Areas to Improve** — 2–3 honest, data-backed weaknesses
4. **Fatigue & Durability** — How did the rider hold up? Any signs of glycogen depletion or drift?
5. **Training Recommendations** — 3 specific, actionable sessions to address weaknesses (give actual intervals/durations)
6. **Coach's Verdict** — One paragraph, honest and direct summary

Use markdown formatting. Be specific with numbers. Keep total response under 700 words."""

    return prompt
