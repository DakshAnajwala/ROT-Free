"""
fit_parser.py
Parses Garmin/Zwift .fit files without external dependencies.
Returns structured session data ready for display and analysis.
"""

import struct
import datetime
from dataclasses import dataclass, field
from typing import Optional

FIT_EPOCH = datetime.datetime(1989, 12, 31, tzinfo=datetime.timezone.utc)
INVALID = {1: 0xFF, 2: 0xFFFF, 4: 0xFFFFFFFF, 8: 0xFFFFFFFFFFFFFFFF}


def _parse_val(raw_bytes: bytes, little_endian: bool = True) -> int:
    n = len(raw_bytes)
    if n == 1:
        return raw_bytes[0]
    fmt_map = {2: "H", 4: "I", 8: "Q"}
    if n in fmt_map:
        endian = "<" if little_endian else ">"
        return struct.unpack(f"{endian}{fmt_map[n]}", raw_bytes)[0]
    return int.from_bytes(raw_bytes, "little" if little_endian else "big")


def _is_invalid(val: int, size: int) -> bool:
    return val == INVALID.get(size, -1)


@dataclass
class SessionData:
    # Overview
    start_datetime: Optional[datetime.datetime] = None
    duration_s: float = 0
    distance_m: float = 0
    avg_speed_ms: float = 0
    max_speed_ms: float = 0
    total_ascent_m: int = 0
    total_descent_m: int = 0
    calories: int = 0
    sport: str = "cycling"

    # HR
    avg_hr: int = 0
    max_hr: int = 0

    # Power
    avg_power: int = 0
    max_power: int = 0
    normalized_power: int = 0

    # Cadence
    avg_cadence: int = 0
    max_cadence: int = 0

    # Time series (second-by-second)
    timestamps: list = field(default_factory=list)   # seconds from start
    power_ts: list = field(default_factory=list)
    hr_ts: list = field(default_factory=list)
    cadence_ts: list = field(default_factory=list)
    speed_ts: list = field(default_factory=list)      # km/h
    altitude_ts: list = field(default_factory=list)   # metres
    distance_ts: list = field(default_factory=list)   # km

    # Laps
    laps: list = field(default_factory=list)          # list of dicts


def parse_fit(file_bytes: bytes) -> SessionData:
    """Parse a .fit file and return a SessionData object."""
    if len(file_bytes) < 14:
        raise ValueError("File too small to be a valid FIT file.")
    if file_bytes[8:12] != b".FIT":
        raise ValueError("Not a valid FIT file (missing .FIT signature).")

    header_size = file_bytes[0]
    data = file_bytes[header_size:]
    pos = 0
    data_len = len(data) - 2  # strip trailing CRC

    local_defs: dict = {}
    last_timestamp: int = 0

    raw_records: list = []   # global_num=20
    raw_sessions: list = []  # global_num=18
    raw_laps: list = []      # global_num=19

    try:
        while pos < data_len:
            rh = data[pos]; pos += 1
            is_comp = (rh & 0x80) != 0

            if is_comp:
                ln = (rh >> 5) & 0x03
                to = rh & 0x1F
                l5 = last_timestamp & 0x1F
                if to >= l5:
                    last_timestamp = (last_timestamp & ~0x1F) | to
                else:
                    last_timestamp = ((last_timestamp & ~0x1F) + 0x20) | to

                if ln in local_defs:
                    defn = local_defs[ln]
                    rec = {253: last_timestamp}
                    for fnum, fsize, _ in defn["nf"]:
                        rb = data[pos:pos + fsize]; pos += fsize
                        if fsize <= 8:
                            v = _parse_val(rb, defn["le"])
                            if not _is_invalid(v, fsize):
                                rec[fnum] = v
                        else:
                            rec[fnum] = rb
                    for _, dfs, _ in defn["df"]:
                        pos += dfs
                    _route(defn["gn"], rec, raw_records, raw_sessions, raw_laps)

            else:
                mt = (rh >> 6) & 0x01
                hd = (rh & 0x20) != 0
                ln = rh & 0x0F

                if mt == 1:  # definition
                    pos += 1
                    arch = data[pos]; pos += 1
                    le = arch == 0
                    gn = struct.unpack("<H" if le else ">H", data[pos:pos + 2])[0]; pos += 2
                    nf = data[pos]; pos += 1
                    nfl = [(data[pos + i * 3], data[pos + i * 3 + 1], data[pos + i * 3 + 2])
                           for i in range(nf)]
                    pos += nf * 3
                    dfl = []
                    if hd:
                        nd = data[pos]; pos += 1
                        dfl = [(data[pos + i * 3], data[pos + i * 3 + 1], data[pos + i * 3 + 2])
                               for i in range(nd)]
                        pos += nd * 3
                    local_defs[ln] = {"gn": gn, "le": le, "nf": nfl, "df": dfl}

                else:  # data
                    if ln in local_defs:
                        defn = local_defs[ln]
                        le = defn["le"]
                        rec = {}
                        for fnum, fsize, _ in defn["nf"]:
                            rb = data[pos:pos + fsize]; pos += fsize
                            if fsize <= 8:
                                v = _parse_val(rb, le)
                                if not _is_invalid(v, fsize):
                                    rec[fnum] = v
                            else:
                                rec[fnum] = rb
                        for _, dfs, _ in defn["df"]:
                            pos += dfs
                        if 253 in rec:
                            last_timestamp = rec[253]
                        _route(defn["gn"], rec, raw_records, raw_sessions, raw_laps)

    except Exception:
        pass  # partial files still return what we have

    return _build_session(raw_records, raw_sessions, raw_laps)


def _route(gn, rec, records, sessions, laps):
    if gn == 20:
        records.append(rec)
    elif gn == 18:
        sessions.append(rec)
    elif gn == 19:
        laps.append(rec)


def _build_session(raw_records, raw_sessions, raw_laps) -> SessionData:
    sd = SessionData()

    # ── Session summary ──────────────────────────────────────────────
    if raw_sessions:
        s = raw_sessions[0]
        # start_time field=2, timestamp=253
        start_ts = s.get(2) or s.get(253)
        if start_ts:
            try:
                sd.start_datetime = FIT_EPOCH + datetime.timedelta(seconds=int(start_ts))
            except Exception:
                pass
        sd.duration_s   = s.get(7, 0) / 1000
        sd.distance_m   = s.get(9, 0) / 100
        sd.avg_speed_ms = s.get(14, 0) / 1000
        sd.max_speed_ms = s.get(15, 0) / 1000
        sd.avg_hr       = s.get(16, 0)
        sd.max_hr       = s.get(17, 0)
        sd.avg_cadence  = s.get(18, 0)
        sd.max_cadence  = s.get(19, 0)
        sd.avg_power    = s.get(20, 0)
        sd.max_power    = s.get(21, 0)
        sd.total_ascent_m   = s.get(22, 0)
        sd.total_descent_m  = s.get(23, 0)
        sd.calories     = s.get(11, 0)
        sport_byte = s.get(5, 2)
        sd.sport = {0: "generic", 1: "running", 2: "cycling",
                    5: "swimming", 11: "walking"}.get(sport_byte, "cycling")

    # ── Time series ───────────────────────────────────────────────────
    recs = sorted(raw_records, key=lambda r: r.get(253, 0))
    if not recs:
        return sd

    start_ts_val = recs[0].get(253, 0)
    if not sd.start_datetime and start_ts_val:
        try:
            sd.start_datetime = FIT_EPOCH + datetime.timedelta(seconds=int(start_ts_val))
        except Exception:
            pass

    for r in recs:
        ts  = r.get(253, 0)
        pwr = r.get(7)
        hr  = r.get(3)
        cad = r.get(4)
        spd = r.get(6)
        alt = r.get(2)
        dist = r.get(5)

        sd.timestamps.append(int(ts) - int(start_ts_val))
        sd.power_ts.append(int(pwr) if pwr and 0 < pwr < 3000 else None)
        sd.hr_ts.append(int(hr) if hr and 30 < hr < 220 else None)
        sd.cadence_ts.append(int(cad) if cad and 5 < cad < 180 else None)
        sd.speed_ts.append(round(spd / 1000 * 3.6, 2) if spd and spd < 50000 else None)
        sd.altitude_ts.append(round(alt / 5 - 500, 1) if alt and alt < 60000 else None)
        sd.distance_ts.append(round(dist / 100 / 1000, 3) if dist and dist < 5000000 else None)

    # Fill session summary from time series if missing
    valid_pwr = [p for p in sd.power_ts if p]
    valid_hr  = [h for h in sd.hr_ts if h]
    valid_cad = [c for c in sd.cadence_ts if c]

    if not sd.avg_power and valid_pwr:
        sd.avg_power = int(sum(valid_pwr) / len(valid_pwr))
    if not sd.max_power and valid_pwr:
        sd.max_power = max(valid_pwr)
    if not sd.avg_hr and valid_hr:
        sd.avg_hr = int(sum(valid_hr) / len(valid_hr))
    if not sd.max_hr and valid_hr:
        sd.max_hr = max(valid_hr)
    if not sd.avg_cadence and valid_cad:
        sd.avg_cadence = int(sum(valid_cad) / len(valid_cad))
    if not sd.max_cadence and valid_cad:
        sd.max_cadence = max(valid_cad)

    # Normalized power
    sd.normalized_power = int(_calc_np(sd.power_ts))

    # ── Laps ──────────────────────────────────────────────────────────
    for i, lap in enumerate(raw_laps):
        lap_time = lap.get(7, 0) / 1000
        lap_dist = lap.get(9, 0) / 100
        sd.laps.append({
            "lap":      i + 1,
            "duration_min": round(lap_time / 60, 1),
            "distance_km":  round(lap_dist / 1000, 2),
            "avg_hr":   lap.get(15) or lap.get(16, 0),
            "max_hr":   lap.get(16) or lap.get(17, 0),
            "avg_power": lap.get(19) or lap.get(20, 0),
            "avg_cadence": lap.get(17) or lap.get(18, 0),
        })

    return sd


def _calc_np(power_series) -> float:
    clean = [p if p else 0 for p in power_series]
    if len(clean) < 30:
        return 0
    rolling = [sum(clean[i - 29:i + 1]) / 30 for i in range(29, len(clean))]
    if not rolling:
        return 0
    return (sum(x ** 4 for x in rolling) / len(rolling)) ** 0.25


def best_effort_watts(power_series, duration_s: int) -> float:
    """Return best average power over a given duration in seconds."""
    clean = [p if p else 0 for p in power_series]
    if len(clean) < duration_s:
        return 0.0
    return max(
        sum(clean[i:i + duration_s]) / duration_s
        for i in range(len(clean) - duration_s + 1)
    )
