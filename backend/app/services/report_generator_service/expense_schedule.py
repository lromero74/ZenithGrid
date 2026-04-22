"""
Expense Schedule — date math and lookahead helpers for expense goal cards.

Part of the report_generator_service package.
"""

from datetime import datetime, timedelta
from typing import List, Optional


# Number of days into the next period to show in the expense lookahead
LOOKAHEAD_DAYS = 15

_DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_ABBREVS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _fmt_coverage_pct(pct: float) -> str:
    """Format expense coverage percentage with adaptive precision.

    Small values get more decimals so they don't misleadingly round to 0%.
    - < 1%  → 2 decimals (e.g. "0.31%")
    - 1-10% → 1 decimal  (e.g. "3.2%")
    - >= 10% → 0 decimals (e.g. "67%")
    """
    if pct < 1:
        return f"{pct:.2f}%"
    elif pct < 10:
        return f"{pct:.1f}%"
    else:
        return f"{pct:.0f}%"


def _ordinal_day(day: int) -> str:
    """Render a due day as ordinal ('1st', '15th') or 'Last' for -1."""
    if day == -1:
        return "Last"
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _next_biweekly_date(anchor_str: str, dow: int, today: datetime) -> datetime:
    """Find the next biweekly occurrence of `dow` based on anchor date.

    Args:
        anchor_str: ISO date string (YYYY-MM-DD) for the anchor/start date.
        dow: Day of week (0=Mon..6=Sun).
        today: Current datetime (only date part used).
    """
    anchor = datetime.strptime(anchor_str, "%Y-%m-%d")
    # If anchor hasn't started yet, return it
    if today.replace(hour=0, minute=0, second=0, microsecond=0) < anchor:
        return anchor
    # Find next occurrence of dow from today
    days_until = (dow - today.weekday()) % 7
    candidate = today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until)
    # Check week parity relative to anchor
    weeks_diff = (candidate - anchor).days // 7
    if weeks_diff % 2 != 0:
        # Off-week — push 7 days forward
        candidate += timedelta(days=7)
    return candidate


def _next_every_n_days_date(anchor_str: str, n: int, today: datetime) -> datetime:
    """Find the next every-N-days occurrence based on anchor date.

    Args:
        anchor_str: ISO date string (YYYY-MM-DD) for the anchor/start date.
        n: Number of days between occurrences.
        today: Current datetime (only date part used).
    """
    import math
    anchor = datetime.strptime(anchor_str, "%Y-%m-%d")
    today_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    # If anchor hasn't started yet, return it
    if today_date < anchor:
        return anchor
    days_elapsed = (today_date - anchor).days
    # ceil to find next multiple of n that's >= days_elapsed
    cycles = math.ceil(days_elapsed / n)
    return anchor + timedelta(days=cycles * n)


def _get_upcoming_items(items: list, now: datetime) -> List:
    """Return upcoming expense items sorted by days until due, scoped to current month.

    Returns list of (sort_key, item) tuples.
    """
    import calendar

    today_day = now.day
    current_month = now.month
    today_dow = now.weekday()
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    _MULTI_MONTH_FREQS = {"quarterly", "semi_annual", "yearly"}
    _WEEKLY_FREQS = {"weekly", "biweekly"}

    upcoming = []
    for item in items:
        dd = item.get("due_day")
        freq = item.get("frequency", "monthly")
        anchor = item.get("frequency_anchor")

        # every_n_days: compute from anchor, no due_day needed
        if freq == "every_n_days" and anchor and item.get("frequency_n"):
            next_dt = _next_every_n_days_date(anchor, item["frequency_n"], now)
            if next_dt.month == now.month and next_dt.year == now.year:
                days_until = (next_dt - today_date).days
                upcoming.append((days_until, item))
            continue

        if dd is None:
            continue

        dm = item.get("due_month")

        if freq in _WEEKLY_FREQS:
            if freq == "biweekly" and anchor:
                next_dt = _next_biweekly_date(anchor, dd, now)
                days_until = (next_dt - today_date).days
            else:
                days_until = (dd - today_dow) % 7
                next_dt = now + timedelta(days=days_until)
            if next_dt.month == now.month and next_dt.year == now.year:
                upcoming.append((days_until, item))
            continue

        # For multi-month frequencies, check if this item is due this month
        if freq in _MULTI_MONTH_FREQS and dm is not None:
            if freq == "yearly" and current_month != dm:
                continue
            elif freq == "semi_annual":
                if current_month not in (dm, ((dm + 5) % 12) + 1):
                    continue
            elif freq == "quarterly":
                quarter_months = {((dm - 1 + 3 * i) % 12) + 1 for i in range(4)}
                if current_month not in quarter_months:
                    continue

        resolved = last_day_of_month if dd == -1 else min(dd, last_day_of_month)
        if resolved >= today_day:
            upcoming.append((resolved, item))

    upcoming.sort(key=lambda x: x[0])
    return upcoming


def _get_lookahead_items(
    items: list, now: datetime, period_window: str,
) -> List:
    """Return expense items due in the first LOOKAHEAD_DAYS of the next period.

    Only applicable for xTD windows (mtd, wtd, qtd, ytd).
    Returns list of (sort_key, item_copy) tuples where item_copy includes
    '_lookahead_due_date' for correct date label rendering.
    """
    import calendar
    from dateutil.relativedelta import relativedelta

    if period_window not in ("mtd", "wtd", "qtd", "ytd"):
        return []

    # Compute next period start and lookahead end
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period_window == "mtd":
        if now.month == 12:
            next_start = today_date.replace(year=now.year + 1, month=1, day=1)
        else:
            next_start = today_date.replace(month=now.month + 1, day=1)
    elif period_window == "wtd":
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_start = today_date + timedelta(days=days_until_monday)
    elif period_window == "qtd":
        q_month = ((now.month - 1) // 3) * 3 + 1
        q_start = today_date.replace(month=q_month, day=1)
        next_start = q_start + relativedelta(months=3)
    elif period_window == "ytd":
        next_start = today_date.replace(year=now.year + 1, month=1, day=1)
    else:
        return []

    lookahead_end = next_start + timedelta(days=LOOKAHEAD_DAYS)

    _MULTI_MONTH_FREQS = {"quarterly", "semi_annual", "yearly"}
    _WEEKLY_FREQS = {"weekly", "biweekly"}

    upcoming = []
    for item in items:
        dd = item.get("due_day")
        freq = item.get("frequency", "monthly")
        anchor = item.get("frequency_anchor")

        # every_n_days: compute next occurrence from next_start onwards
        if freq == "every_n_days" and anchor and item.get("frequency_n"):
            next_dt = _next_every_n_days_date(
                anchor, item["frequency_n"], next_start
            )
            if next_start <= next_dt < lookahead_end:
                days_from_start = (next_dt - next_start).days
                item_copy = dict(item)
                item_copy["_lookahead_due_date"] = next_dt
                upcoming.append((days_from_start, item_copy))
            continue

        if dd is None:
            continue

        dm = item.get("due_month")

        if freq in _WEEKLY_FREQS:
            if freq == "biweekly" and anchor:
                next_dt = _next_biweekly_date(anchor, dd, next_start)
            else:
                days_until = (dd - next_start.weekday()) % 7
                next_dt = next_start + timedelta(days=days_until)
            if next_start <= next_dt < lookahead_end:
                days_from_start = (next_dt - next_start).days
                item_copy = dict(item)
                item_copy["_lookahead_due_date"] = next_dt
                upcoming.append((days_from_start, item_copy))
            continue

        # Monthly and multi-month frequencies
        check_month = next_start.month
        check_year = next_start.year

        if freq in _MULTI_MONTH_FREQS and dm is not None:
            if freq == "yearly" and check_month != dm:
                continue
            elif freq == "semi_annual":
                if check_month not in (dm, ((dm + 5) % 12) + 1):
                    continue
            elif freq == "quarterly":
                quarter_months = {
                    ((dm - 1 + 3 * i) % 12) + 1 for i in range(4)
                }
                if check_month not in quarter_months:
                    continue

        last_day = calendar.monthrange(check_year, check_month)[1]
        resolved = last_day if dd == -1 else min(dd, last_day)

        try:
            due_date = next_start.replace(day=resolved)
        except ValueError:
            continue

        if next_start <= due_date < lookahead_end:
            days_from_start = (due_date - next_start).days
            item_copy = dict(item)
            item_copy["_lookahead_due_date"] = due_date
            upcoming.append((days_from_start, item_copy))

    upcoming.sort(key=lambda x: x[0])
    return upcoming


def _format_due_label(item: dict, now: Optional[datetime] = None) -> str:
    """Format a human-readable due label for an expense item."""
    freq = item.get("frequency", "monthly")
    dd = item.get("due_day")
    anchor = item.get("frequency_anchor")

    # every_n_days: compute from anchor, no due_day needed
    if freq == "every_n_days" and anchor and item.get("frequency_n"):
        if not now:
            return ""
        next_dt = _next_every_n_days_date(anchor, item["frequency_n"], now)
        return f"{_MONTH_ABBREVS[next_dt.month - 1]} {_ordinal_day(next_dt.day)}"

    if dd is None:
        return ""

    if freq in ("weekly", "biweekly"):
        dow_name = _DOW_NAMES[dd] if 0 <= dd <= 6 else str(dd)
        if now and 0 <= dd <= 6:
            # Use anchor-aware calc for biweekly if anchor is set
            if freq == "biweekly" and anchor:
                next_date = _next_biweekly_date(anchor, dd, now)
            else:
                days_until = (dd - now.weekday()) % 7
                next_date = now + timedelta(days=days_until)
            mon = _MONTH_ABBREVS[next_date.month - 1]
            return f"{dow_name} {mon} {_ordinal_day(next_date.day)}"
        return dow_name

    dm = item.get("due_month")
    day_str = _ordinal_day(dd)
    if freq in ("quarterly", "semi_annual", "yearly") and dm and 1 <= dm <= 12:
        return f"{_MONTH_ABBREVS[dm - 1]} {day_str}"
    # monthly/semi_monthly: show current month
    if now:
        return f"{_MONTH_ABBREVS[now.month - 1]} {day_str}"
    return day_str
