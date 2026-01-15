from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any


def _parse_iso(dt_str: str) -> datetime:
    """
    Parse ISO-8601 timestamps safely.
    Accepts:
      - 2026-01-15T17:00:00-04:00
      - 2026-01-15T21:00:00Z
    """
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _to_iso(dt: datetime) -> str:
    """
    Return ISO string (keeps timezone info if dt is aware).
    """
    return dt.isoformat()


@dataclass
class Slot:
    start: datetime
    end: datetime
    score: float
    reason: str


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            merged[-1] = (last_s, max(last_e, e))
        else:
            merged.append((s, e))
    return merged


def _extract_busy_intervals(freebusy_response: Dict[str, Any]) -> List[Tuple[datetime, datetime]]:
    """
    freebusy_response is Google API response:
      { calendars: { primary: { busy: [{start, end}, ...] } } }
    Busy start/end often come back in UTC with 'Z'.
    """
    busy = freebusy_response.get("calendars", {}).get("primary", {}).get("busy", [])
    out: List[Tuple[datetime, datetime]] = []
    for b in busy:
        bs = _parse_iso(b["start"])
        be = _parse_iso(b["end"])
        out.append((bs, be))
    return _merge_intervals(out)


def propose_free_slots(
    window_start_iso: str,
    window_end_iso: str,
    duration_minutes: int,
    limit: int,
    freebusy_response: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Rule-based: return the earliest free slots of length duration_minutes
    within [window_start, window_end], using Google freebusy busy blocks.
    """
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be > 0")
    if limit <= 0:
        raise ValueError("limit must be > 0")

    window_start = _parse_iso(window_start_iso)
    window_end = _parse_iso(window_end_iso)

    if window_end <= window_start:
        raise ValueError("end must be after start")

    busy_intervals = _extract_busy_intervals(freebusy_response)

    # Build free gaps in [window_start, window_end]
    free_gaps: List[Tuple[datetime, datetime]] = []
    cursor = window_start

    for bs, be in busy_intervals:
        # If busy interval is completely outside our window, ignore
        if be <= window_start or bs >= window_end:
            continue

        bs_clamped = max(bs, window_start)
        be_clamped = min(be, window_end)

        if bs_clamped > cursor:
            free_gaps.append((cursor, bs_clamped))
        cursor = max(cursor, be_clamped)

    if cursor < window_end:
        free_gaps.append((cursor, window_end))

    # From each free gap, carve slots of duration_minutes (earliest-first)
    dur = timedelta(minutes=duration_minutes)
    slots: List[Slot] = []
    for fs, fe in free_gaps:
        t = fs
        while t + dur <= fe:
            slots.append(
                Slot(
                    start=t,
                    end=t + dur,
                    score=1.0,  # simple scoring for MVP
                    reason="Earliest available slot in requested window",
                )
            )
            t = t + dur  # step by duration; (later you can step by 5/10 mins)

    slots = slots[:limit]

    return {
        "window": {"start": window_start_iso, "end": window_end_iso},
        "duration_minutes": duration_minutes,
        "limit": limit,
        "busy_blocks": len(busy_intervals),
        "proposals": [
            {
                "start": _to_iso(s.start),
                "end": _to_iso(s.end),
                "score": s.score,
                "reason": s.reason,
            }
            for s in slots
        ],
    }
