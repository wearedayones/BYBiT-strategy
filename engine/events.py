"""
Event schedule for the bracket strategy.

"Events" are scheduled market inflection points where volatility spikes and
directional breakouts are likely. For Bybit perpetuals the canonical events are:

  — Funding rate resets: 00:00, 08:00, 16:00 UTC (every 8 hours)
  — Major session opens: Asia (00:00 UTC), London (08:00 UTC), New York (13:30 UTC)
  — Daily candle close: 00:00 UTC (same as funding + Asia open)

Additional user-defined events can be added to settings.yaml in future.

The pre-event window (default 45 min before) is where consolidation is expected;
the bracket is placed 5–10 min before the event.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Literal


@dataclasses.dataclass
class ScheduledEvent:
    name: str
    event_type: Literal["funding", "session_open", "daily_close"]
    utc_time: datetime
    minutes_away: float    # positive = in the future


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _next_occurrence(hour: int, minute: int = 0, now: datetime | None = None) -> datetime:
    """Return the next UTC datetime when the clock reads HH:MM."""
    if now is None:
        now = _utc_now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def upcoming_events(
    now: datetime | None = None,
    horizon_hours: int = 10,
) -> list[ScheduledEvent]:
    """
    Return all scheduled events within the next `horizon_hours`, sorted ascending.

    Funding resets and session opens for Bybit perpetuals.
    """
    if now is None:
        now = _utc_now()

    event_specs = [
        # (hour, minute, name, type)
        (0, 0, "Asia open / Daily close / Funding", "funding"),
        (8, 0, "London open / Funding", "funding"),
        (13, 30, "New York open", "session_open"),
        (16, 0, "Funding reset", "funding"),
    ]

    events: list[ScheduledEvent] = []
    cutoff = now + timedelta(hours=horizon_hours)

    for hour, minute, name, etype in event_specs:
        t = _next_occurrence(hour, minute, now)
        # include today's occurrence if it's still upcoming
        today_candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today_candidate > now:
            t = today_candidate
        while t <= cutoff:
            delta = (t - now).total_seconds() / 60
            events.append(ScheduledEvent(
                name=name,
                event_type=etype,
                utc_time=t,
                minutes_away=delta,
            ))
            t += timedelta(days=1)

    events.sort(key=lambda e: e.utc_time)
    return events


def next_event(now: datetime | None = None) -> ScheduledEvent | None:
    """Convenience: the single next event."""
    evs = upcoming_events(now=now, horizon_hours=10)
    return evs[0] if evs else None


def is_in_pre_event_window(
    now: datetime | None = None,
    window_minutes: int = 45,
    min_minutes_away: float = 5.0,
) -> tuple[bool, ScheduledEvent | None]:
    """
    True if we are within [min_minutes_away, window_minutes] before any event.
    The lower bound prevents entering a bracket with no time before the event fires.

    Returns (in_window, event).
    """
    ne = next_event(now)
    if ne is None:
        return False, None
    in_window = min_minutes_away <= ne.minutes_away <= window_minutes
    return in_window, (ne if in_window else None)


def minutes_to_next_funding(now: datetime | None = None) -> float:
    """How many minutes until the next 8-hourly funding reset."""
    if now is None:
        now = _utc_now()
    funding_hours = [0, 8, 16]
    candidates = []
    for h in funding_hours:
        t = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        candidates.append(t)
    nxt = min(candidates)
    return (nxt - now).total_seconds() / 60
