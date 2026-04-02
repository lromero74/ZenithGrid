"""
Expense Builder — expense goal cards, schedule helpers, upcoming/lookahead.

Part of the report_generator_service package.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


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


def _build_expense_status_badge(item: dict) -> str:
    """Return an HTML badge span for an expense item's coverage status."""
    status = item.get("status", "uncovered")
    if status == "covered":
        badge_bg, badge_color, badge_text = "#065f46", "#6ee7b7", "Covered"
    elif status == "partial":
        cp = item.get("coverage_pct", 0)
        badge_bg, badge_color, badge_text = "#78350f", "#fcd34d", _fmt_coverage_pct(cp)
    elif status == "blocked":
        badge_bg, badge_color, badge_text = "#1e1b4b", "#a5b4fc", "Blocked"
    else:
        badge_bg, badge_color, badge_text = "#7f1d1d", "#fca5a5", "Uncovered"
    return (
        f'<span style="background: {badge_bg}; color: {badge_color};'
        f' padding: 1px 6px; border-radius: 4px; font-size: 10px;'
        f' font-weight: 600;">{badge_text}</span>'
    )


def _build_savings_status_badge(entry: dict) -> str:
    """Return an HTML badge for a savings target's status."""
    status = entry.get("status", "pending")
    on_track = entry.get("dynamic_on_track", False) or entry.get("savings_on_track", False)
    is_ready = entry.get("is_ready", False)
    if is_ready:
        return (
            '<span style="background:#1e3a5f; color:#93c5fd; padding:1px 6px;'
            ' border-radius:4px; font-size:10px; font-weight:600;">Ready</span>'
        )
    if status == "funded" or on_track:
        return (
            '<span style="background:#065f46; color:#6ee7b7; padding:1px 6px;'
            ' border-radius:4px; font-size:10px; font-weight:600;">On Track</span>'
        )
    elif status == "past_due":
        return (
            '<span style="background:#7f1d1d; color:#fca5a5; padding:1px 6px;'
            ' border-radius:4px; font-size:10px; font-weight:600;">Past Due</span>'
        )
    elif status == "blocked":
        return (
            '<span style="background:#1e1b4b; color:#a5b4fc; padding:1px 6px;'
            ' border-radius:4px; font-size:10px; font-weight:600;">Blocked</span>'
        )
    elif status == "partial":
        pct = entry.get("coverage_pct", 0)
        return (
            f'<span style="background:#78350f; color:#fcd34d; padding:1px 6px;'
            f' border-radius:4px; font-size:10px; font-weight:600;">'
            f'Behind ({_fmt_coverage_pct(pct)})</span>'
        )
    else:
        return (
            '<span style="background:#78350f; color:#fcd34d; padding:1px 6px;'
            ' border-radius:4px; font-size:10px; font-weight:600;">Behind</span>'
        )


def _spend_line(prefix: str, fmt: str, target_amt: float, gross_target: float,
                tax_amount: float = 0.0, recurrence_hold: float = 0.0) -> str:
    """Return a spend summary line with optional Tax/Hold breakdown.

    Plain:     Spend: $25.00
    With tax:  Spend: $25.00 · Tax: $8.33 → accumulate: $33.33
    Full:      Spend: $25.00 · Tax: $8.33 · Hold: $12.00 → accumulate: $45.33
    """
    base = f"Spend:&nbsp;{prefix}{target_amt:{fmt}}"
    if gross_target <= target_amt + 0.01:
        return base

    parts = [base]
    if tax_amount > 0.01:
        parts.append(f"Tax:&nbsp;{prefix}{tax_amount:{fmt}}")
    if recurrence_hold > 0.01:
        parts.append(f"Hold:&nbsp;{prefix}{recurrence_hold:{fmt}}")
    return (
        "&nbsp;&middot;&nbsp;".join(parts)
        + f"&nbsp;&rarr;&nbsp;accumulate:&nbsp;{prefix}{gross_target:{fmt}}"
    )


def _build_savings_targets_html(
    savings_targets: list, prefix: str, fmt: str, currency: str,
    period: str, coverage: dict,
) -> str:
    """Build the Savings Targets section rendered below the expense table.

    Uses capital-reservation framing:
    - "Reserved: $X ✓" when dynamic_reserved >= capital_required (funded by growth)
    - "Need $X | Reserved $Y | Gap $Z" when behind
    - Growth rate source badge (auto = from live account return)
    """
    if not savings_targets:
        return ""

    rows = ""
    for entry in savings_targets:
        name = entry.get("name", "")
        target_amt = entry.get("target_amount", 0)
        gross_target = entry.get("gross_target", target_amt)
        target_date = entry.get("target_date", "")
        cap_req = entry.get("capital_required", 0)
        dynamic_res = entry.get("dynamic_reserved", entry.get("current_balance", 0))
        cap_gap = entry.get("capital_gap", max(0.0, cap_req - dynamic_res))
        months_remaining = entry.get("months_remaining", 0)
        growth_rate = entry.get("assumed_growth_rate_pct", 0) or 0
        rate_source = entry.get("growth_rate_source", "account")
        monthly_contrib = entry.get("monthly_contribution", 0)
        is_recurring = entry.get("is_recurring", False)
        tax_amount = entry.get("tax_amount", 0.0)
        recurrence_hold = entry.get("recurrence_hold", 0.0)
        on_track = cap_gap <= 0
        badge = _build_savings_status_badge(entry)

        # Rate label
        if growth_rate > 0:
            rate_src = " (auto)" if rate_source == "account" else " (override)"
            rate_label = f'<span style="color:#94a3b8; font-size:10px;">{growth_rate:.1f}%/yr{rate_src}</span>'
        else:
            rate_label = '<span style="color:#64748b; font-size:10px;">no growth rate</span>'

        # Target date + recurrence hint
        date_str = target_date[:7] if target_date else "?"
        recur_hint = " ↻" if is_recurring else ""

        # Reservation status line
        if on_track:
            res_html = (
                f'<span style="color:#6ee7b7; font-size:11px;">'
                f'Reserved: {prefix}{dynamic_res:{fmt}} ✓&nbsp;—&nbsp;funded by growth</span>'
            )
        elif cap_req > 0:
            res_parts = [
                f'<span style="color:#94a3b8;">Need&nbsp;{prefix}{cap_req:{fmt}}</span>'
            ]
            if dynamic_res > 0:
                res_parts.append(
                    f'<span style="color:#94a3b8;">reserved&nbsp;{prefix}{dynamic_res:{fmt}}</span>'
                )
            res_parts.append(
                f'<span style="color:#fbbf24;">gap&nbsp;{prefix}{cap_gap:{fmt}}</span>'
            )
            if monthly_contrib > 0:
                res_parts.append(
                    f'<span style="color:#94a3b8;">'
                    f'or&nbsp;{prefix}{monthly_contrib:{fmt}}/mo&nbsp;from&nbsp;income</span>'
                )
            res_html = (
                '&nbsp;<span style="color:#475569;">|</span>&nbsp;'.join(res_parts)
            )
        else:
            res_html = '<span style="color:#64748b; font-size:11px;">no target date</span>'

        rows += f"""
            <tr>
                <td style="padding:5px 6px 5px 0; vertical-align:top;">
                    <div style="color:#f1f5f9; font-size:12px; font-weight:600;">
                        {name}{recur_hint}</div>
                    <div style="color:#94a3b8; font-size:10px; margin-top:1px;">
                        {_spend_line(prefix, fmt, target_amt, gross_target, tax_amount, recurrence_hold)} by {date_str}
                        &nbsp;·&nbsp;{months_remaining}mo&nbsp;·&nbsp;{rate_label}
                    </div>
                </td>
                <td style="padding:5px 0; vertical-align:top; font-size:11px;">
                    {res_html}
                </td>
                <td style="padding:5px 0 5px 8px; vertical-align:top; text-align:right; white-space:nowrap;">
                    {badge}
                </td>
            </tr>"""

    total_savings = coverage.get("total_savings_contributions", 0)
    income_earmarked = coverage.get("income_earmarked_for_savings", 0)
    free_balance = coverage.get("free_balance", None)

    footer_parts = []
    if income_earmarked > 0:
        footer_parts.append(
            f'Income earmarked for savings: {prefix}{income_earmarked:{fmt}} {currency}/{period}'
        )
    if free_balance is not None:
        footer_parts.append(
            f'Free balance after reservations: {prefix}{free_balance:{fmt}} {currency}'
        )
    footer_html = ""
    if footer_parts:
        footer_html = (
            '<div style="margin-top:8px; padding-top:8px; border-top:1px solid #334155;'
            ' color:#64748b; font-size:10px;">'
            + '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(footer_parts)
            + '</div>'
        )

    _ = total_savings  # available if needed for future summary line

    return f"""
        <div style="margin-top:14px; padding-top:10px; border-top:2px solid #1e3a5f;">
            <div style="color:#10b981; font-size:11px; font-weight:700; margin-bottom:6px;
                        text-transform:uppercase; letter-spacing:0.05em;">
                &#127383; Savings Targets
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:11px;">
                <tr>
                    <th style="padding:2px 0; color:#64748b; font-size:10px; text-align:left;
                               font-weight:600; width:45%;">Goal</th>
                    <th style="padding:2px 0; color:#64748b; font-size:10px; text-align:left;
                               font-weight:600;">Reservation</th>
                    <th style="padding:2px 0; color:#64748b; font-size:10px; text-align:right;
                               font-weight:600; width:80px;">Status</th>
                </tr>
                {rows}
            </table>
            {footer_html}
        </div>"""


def _build_expense_changes_html(
    changes: Optional[Dict[str, Any]],
    prefix: str,
    fmt: str,
) -> str:
    """Render 'Changes from Prior Report' section for an expense goal.

    Args:
        changes: Dict with optional keys: increased, decreased, added, removed.
        prefix: Currency prefix ("$" or "").
        fmt: Format string for amounts (",.2f" or ".8f").

    Returns:
        HTML string, or "" if no changes.
    """
    if not changes:
        return ""

    sections = []

    _section_config = [
        ("increased", "Increased", "#ef4444", True),
        ("decreased", "Decreased", "#10b981", True),
        ("added", "Added", "#f59e0b", False),
        ("removed", "Removed", "#10b981", False),
    ]

    for key, label, color, show_delta in _section_config:
        items = changes.get(key)
        if not items:
            continue

        rows = ""
        for item in items:
            name = item.get("name", "")
            amount = item.get("amount", 0)

            if show_delta:
                delta = item.get("delta", 0)
                pct = item.get("pct_delta", 0)
                sign = "+" if delta >= 0 else "-"
                abs_delta = abs(delta)
                abs_pct = abs(pct)
                delta_str = (
                    f'{sign}{prefix}{abs_delta:{fmt}}'
                    f' ({sign}{abs_pct:.1f}%)'
                )
            elif key == "added":
                delta_str = "(new)"
            else:
                delta_str = "(removed)"

            amt_prefix = "-" if key == "removed" else ""
            rows += (
                f'<div style="display: flex; justify-content: space-between;'
                f' align-items: center; padding: 2px 0;">'
                f'<span style="color: #e2e8f0; font-size: 12px;">{name}</span>'
                f'<span style="color: {color}; font-size: 12px; white-space: nowrap;">'
                f'{amt_prefix}{prefix}{amount:{fmt}}'
                f'&nbsp;&nbsp;'
                f'<span style="font-size: 11px;">{delta_str}</span>'
                f'</span>'
                f'</div>'
            )

        sections.append(
            f'<div style="margin-bottom: 6px;">'
            f'<p style="color: {color}; font-size: 10px; font-weight: 600;'
            f' text-transform: uppercase; letter-spacing: 0.5px;'
            f' margin: 0 0 2px 0;">{label}</p>'
            f'{rows}</div>'
        )

    if not sections:
        return ""

    return (
        f'<div style="border-top: 1px dashed #334155; margin-top: 10px;'
        f' padding-top: 8px;">'
        f'<p style="color: #94a3b8; font-size: 11px; font-weight: 600;'
        f' margin: 0 0 6px 0;">Changes from Prior Report</p>'
        f'{"".join(sections)}'
        f'</div>'
    )


def _expense_name_html(item: dict, color: str = "#f1f5f9") -> str:
    """Render expense name, linked to login_url if set."""
    name = item.get("name", "")
    url = item.get("login_url")
    if url:
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer"'
            f' style="color: {color}; text-decoration: underline;'
            f' text-decoration-color: #475569;">{name}</a>'
        )
    return name


def _build_expense_coverage_html(
    g: Dict[str, Any], coverage: Dict[str, Any], items: list,
    prefix: str, fmt: str, currency: str, period: str, tax_pct: float,
    savings_targets: Optional[list] = None,
) -> str:
    """Build the Coverage tab: summary stats, item table, savings targets, deposit hints, changes."""
    total_exp = coverage.get("total_expenses", 0)
    total_claims = coverage.get("total_claims", total_exp)
    income_at = coverage.get("income_after_tax", 0)
    covered = coverage.get("covered_count", 0)
    total = coverage.get("total_count", 0)

    # Merge expense items and savings targets by sort_order for interleaved display
    _expense_rows = [("expense", e) for e in items]
    _savings_rows = [("savings", s) for s in (savings_targets or [])]
    _all_rows = sorted(_expense_rows + _savings_rows, key=lambda x: x[1].get("sort_order", 0))

    item_rows = ""
    for row_type, row_item in _all_rows:
        if row_type == "savings":
            # Condensed savings target row — full detail is in the Savings Targets section
            st_name = row_item.get("name", "")
            recur = " ↻" if row_item.get("is_recurring") else ""
            st_status = row_item.get("status", "")
            cap_req = row_item.get("capital_required", 0) or 0
            dyn_res = row_item.get("dynamic_reserved", row_item.get("current_balance", 0)) or 0
            cap_gap = row_item.get("capital_gap", max(0.0, cap_req - dyn_res)) or 0
            if st_status == "blocked":
                res_text = f'Blocked&nbsp;(need&nbsp;{prefix}{cap_req:{fmt}})'
                res_color = "#a5b4fc"
            elif cap_gap <= 0 and cap_req > 0:
                res_text = f'Reserved:&nbsp;{prefix}{dyn_res:{fmt}}&nbsp;✓'
                res_color = "#6ee7b7"
            elif cap_req > 0:
                funded_pct = round(dyn_res / cap_req * 100, 0) if cap_req > 0 else 0
                res_text = (
                    f'{funded_pct:.0f}%&nbsp;funded&nbsp;'
                    f'({prefix}{dyn_res:{fmt}}&nbsp;/&nbsp;{prefix}{cap_req:{fmt}})'
                )
                res_color = "#fbbf24"
            else:
                res_text = "no target set"
                res_color = "#64748b"
            item_rows += f"""
            <tr style="background-color:#0a2a1f;">
                <td style="padding: 4px 0; font-size: 10px; font-weight:600;">
                    <span style="color:#10b981;">&#128180;&nbsp;Savings</span></td>
                <td style="padding: 4px 0; color: #6ee7b7; font-size: 12px; font-weight:600;">
                    {st_name}{recur}</td>
                <td style="padding: 4px 0; text-align: right; font-size: 11px; color:{res_color};">
                    {res_text}</td>
                <td style="padding: 4px 6px; text-align: center;">
                    {_build_savings_status_badge(row_item)}</td>
            </tr>"""
        else:
            norm = row_item.get("normalized_amount", 0)
            if row_item.get("amount_mode") == "percent_of_income":
                pct_val = row_item.get("percent_of_income", 0)
                basis_lbl = row_item.get("percent_basis", "pre_tax")
                basis_str = "pre-tax" if basis_lbl == "pre_tax" else "post-tax"
                amt_html = (
                    f'{prefix}{norm:{fmt}}'
                    f'<br><span style="color:#94a3b8;font-size:10px;">'
                    f'{pct_val:g}% {basis_str}</span>'
                )
            else:
                amt_html = f"{prefix}{norm:{fmt}}"
            item_rows += f"""
            <tr>
                <td style="padding: 4px 0; color: #94a3b8; font-size: 11px;">
                    {row_item.get('category', '')}</td>
                <td style="padding: 4px 0; color: #f1f5f9; font-size: 12px;">
                    {_expense_name_html(row_item)}</td>
                <td style="padding: 4px 0; color: #f1f5f9; text-align: right; font-size: 12px;">
                    {amt_html}</td>
                <td style="padding: 4px 6px; text-align: center;">
                    {_build_expense_status_badge(row_item)}</td>
            </tr>"""

    dep_line = _build_deposit_hints_html(g, coverage, prefix, fmt, currency)

    tax_line = ""
    if tax_pct > 0:
        tax_line = f"""
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Tax Withholding</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {tax_pct:.1f}%</td>
                </tr>"""

    changes_html = _build_expense_changes_html(
        g.get("expense_changes"), prefix, fmt,
    )

    savings_html = _build_savings_targets_html(
        savings_targets or [], prefix, fmt, currency, period, coverage,
    )

    # Show "Total Claims" row only when there are savings targets
    claims_row = ""
    if savings_targets:
        surplus = income_at - total_claims
        surplus_color = "#6ee7b7" if surplus >= 0 else "#fca5a5"
        surplus_sign = "+" if surplus >= 0 else ""
        claims_row = f"""
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Total Claims (exp + savings)</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{total_claims:{fmt}} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Surplus / Shortfall</td>
                    <td style="padding: 4px 0; color: {surplus_color}; text-align: right;
                               font-weight: 600;">
                        {surplus_sign}{prefix}{abs(surplus):{fmt}} {currency}/{period}</td>
                </tr>"""

    return f"""
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;
                          margin-bottom: 10px;">
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Total Expenses</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{total_exp:{fmt}} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Income After Tax</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{income_at:{fmt}} {currency}/{period}</td>
                </tr>{tax_line}{claims_row}
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Items Covered</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {covered} / {total}</td>
                </tr>
            </table>
            <table style="width: 100%; border-collapse: collapse; border-top: 1px solid #334155;
                          padding-top: 8px;">
                <tr>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Category</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Name</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: right;
                               font-weight: 600;">Amount</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: center;
                               font-weight: 600;">Status</th>
                </tr>
                {item_rows}
            </table>
            {savings_html}
            {changes_html}
            {dep_line}"""


def _build_deposit_hints_html(
    g: Dict[str, Any], coverage: Dict[str, Any],
    prefix: str, fmt: str, currency: str,
) -> str:
    """Build deposit-needed hint lines for the coverage tab."""
    dep = g.get("deposit_needed")
    dep_partial = g.get("deposit_partial")
    dep_next = g.get("deposit_next")
    # Labels may come from the goal dict (savings-gap path) or from coverage (expense path)
    partial_name = coverage.get("partial_item_name") or g.get("deposit_partial_label")
    next_name = coverage.get("next_uncovered_name") or g.get("deposit_next_label")

    if dep is None and not partial_name and not next_name:
        return ""

    dep_parts = []

    if partial_name and dep_partial is not None:
        # Savings-gap coaching uses a capital-reservation framing
        savings_gap = coverage.get("first_gap_savings_cap_gap")
        if savings_gap and savings_gap > 0 and partial_name == g.get("deposit_partial_label"):
            dep_parts.append(
                f"Fund <strong>{partial_name}</strong> savings goal: "
                f"deposit ~{prefix}{dep_partial:{fmt}} {currency}"
            )
        else:
            dep_parts.append(
                f"Finish covering <strong>{partial_name}</strong>: "
                f"deposit ~{prefix}{dep_partial:{fmt}} {currency}"
            )
        if next_name and dep_next is not None:
            dep_parts.append(
                f"Also cover <strong>{next_name}</strong>: "
                f"deposit ~{prefix}{dep_next:{fmt}} {currency} total"
            )
    elif next_name and dep_next is not None:
        dep_parts.append(
            f"Cover <strong>{next_name}</strong>: "
            f"deposit ~{prefix}{dep_next:{fmt}} {currency}"
        )

    if dep is not None:
        already_mentioned = (dep_partial or 0) + (dep_next or 0)
        additional = dep - already_mentioned
        if additional > 0 and already_mentioned > 0:
            dep_parts.append(
                f"Cover all listed expenses: ~{prefix}{dep:{fmt}} {currency} total"
                f" (+{prefix}{additional:{fmt}} {currency})"
            )
        else:
            dep_parts.append(
                f"Cover all listed expenses: deposit ~{prefix}{dep:{fmt}} {currency} total"
            )

    return "".join(
        f'<p style="color: #94a3b8; font-size: 11px; margin: {4 if i else 8}px 0 0 0;">'
        f'{part}</p>'
        for i, part in enumerate(dep_parts)
    )


def _build_expense_upcoming_html(
    items: list, prefix: str, fmt: str,
    schedule_meta: Optional[Dict[str, Any]],
) -> str:
    """Build the Upcoming tab: upcoming items table + lookahead preview."""
    now = datetime.utcnow()
    upcoming_raw = _get_upcoming_items(items, now)
    upcoming_items = [(sort_key, item.get("due_day"), item) for sort_key, item in upcoming_raw]

    has_any_due_day = any(
        item.get("due_day") is not None
        or (item.get("frequency") == "every_n_days" and item.get("frequency_anchor"))
        for item in items
    )
    if not upcoming_items and not has_any_due_day:
        content = (
            '<p style="color: #64748b; font-size: 12px; text-align: center; padding: 16px 0;">'
            'Set due dates on your expenses to see upcoming bills</p>'
        )
    elif not upcoming_items:
        content = (
            '<p style="color: #64748b; font-size: 12px; text-align: center; padding: 16px 0;">'
            'No upcoming expenses due this month</p>'
        )
    else:
        upcoming_rows = ""
        for _, dd, item in upcoming_items:
            bill_amount = item.get("amount", 0)
            due_label = _format_due_label(item, now=now)
            upcoming_rows += f"""
                <tr>
                    <td style="padding: 4px 0; color: #e2e8f0; font-size: 12px;
                               font-weight: 600;">{due_label}</td>
                    <td style="padding: 4px 0; color: #94a3b8; font-size: 11px;">
                        {item.get('category', '')}</td>
                    <td style="padding: 4px 0; color: #f1f5f9; font-size: 12px;">
                        {_expense_name_html(item)}</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right; font-size: 12px;">
                        {prefix}{bill_amount:{fmt}}</td>
                    <td style="padding: 4px 6px; text-align: center;">
                        {_build_expense_status_badge(item)}</td>
                </tr>"""
        content = f"""
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Due</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Category</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Name</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: right;
                               font-weight: 600;">Amount</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: center;
                               font-weight: 600;">Status</th>
                </tr>
                {upcoming_rows}
            </table>"""

    # Append lookahead preview if applicable
    content += _build_expense_lookahead_html(items, now, prefix, fmt, schedule_meta)
    return content


def _build_expense_lookahead_html(
    items: list, now: datetime, prefix: str, fmt: str,
    schedule_meta: Optional[Dict[str, Any]],
) -> str:
    """Build the lookahead (next period preview) section appended to upcoming."""
    meta = schedule_meta or {}
    pw = meta.get("period_window", "full_prior")
    show_lookahead = meta.get("show_expense_lookahead", True)

    if not (show_lookahead and pw in ("mtd", "wtd", "qtd", "ytd") and items):
        return ""

    lookahead_raw = _get_lookahead_items(items, now, pw)
    if not lookahead_raw:
        return ""

    _period_labels = {
        "mtd": "Next Month", "wtd": "Next Week",
        "qtd": "Next Quarter", "ytd": "Next Year",
    }
    la_label = _period_labels.get(pw, "Next Period")

    lookahead_rows = ""
    for _, la_item in lookahead_raw:
        bill_amount = la_item.get("amount", 0)
        due_date = la_item.get("_lookahead_due_date")
        if due_date:
            due_label = (
                f"{_MONTH_ABBREVS[due_date.month - 1]} "
                f"{_ordinal_day(due_date.day)}"
            )
        else:
            due_label = _format_due_label(la_item, now=now)
        lookahead_rows += f"""
                    <tr style="opacity: 0.5;">
                        <td style="padding: 4px 0; color: #94a3b8; font-size: 12px;
                                   font-weight: 600;">{due_label}</td>
                        <td style="padding: 4px 0; color: #64748b; font-size: 11px;">
                            {la_item.get('category', '')}</td>
                        <td style="padding: 4px 0; color: #94a3b8; font-size: 12px;">
                            {_expense_name_html(la_item, color="#94a3b8")}</td>
                        <td style="padding: 4px 0; color: #94a3b8; text-align: right;
                                   font-size: 12px;">
                            {prefix}{bill_amount:{fmt}}</td>
                        <td style="padding: 4px 6px; text-align: center;">
                            {_build_expense_status_badge(la_item)}</td>
                    </tr>"""

    return f"""
                <div style="margin-top: 12px; padding-top: 8px;
                            border-top: 1px dashed #334155;">
                    <p style="color: #475569; font-size: 10px; font-weight: 600;
                              text-transform: uppercase; letter-spacing: 0.5px;
                              margin: 0 0 6px 0;">
                        {la_label} Preview</p>
                    <table style="width: 100%; border-collapse: collapse;">
                        {lookahead_rows}
                    </table>
                </div>"""


def _build_expense_projection_html(
    g: Dict[str, Any],
    prefix: str, fmt: str, currency: str, period: str,
    total_exp: float, tax_pct: float,
) -> str:
    """Build the Projections section: income projections + deposit needed."""
    daily_inc = g.get("current_daily_income", 0)
    proj_linear = g.get("projected_income")
    proj_compound = g.get("projected_income_compound")

    if not (daily_inc or proj_linear or proj_compound):
        return ""

    sample = g.get("sample_trades", 0)
    lookback = g.get("lookback_days_used", 0)
    dep = g.get("deposit_needed")
    dep_compound = g.get("deposit_needed_compound")

    after_tax_factor = (1 - tax_pct / 100) if tax_pct < 100 else 0
    linear_at = (proj_linear or 0) * after_tax_factor
    compound_at = (proj_compound or 0) * after_tax_factor

    dep_lin_str = f"{prefix}{dep:{fmt}}" if dep is not None else "N/A"
    dep_cmp_str = f"{prefix}{dep_compound:{fmt}}" if dep_compound is not None else "N/A"

    return f"""
            <div style="border-top: 1px solid #334155; margin-top: 10px; padding-top: 10px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Target</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{total_exp:{fmt}} {currency}/{period}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Daily Avg Income</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{daily_inc:{fmt}} {currency}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Linear Projection</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{linear_at:{fmt}} {currency}/{period} (after tax)</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Compound Projection</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{compound_at:{fmt}} {currency}/{period} (after tax)</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Deposit Needed (Linear)</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {dep_lin_str}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Deposit Needed (Compound)</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {dep_cmp_str}</td>
                    </tr>
                </table>
                <p style="color: #64748b; font-size: 11px; margin: 8px 0 0 0;">
                    Based on {sample} trades over {lookback} days</p>
                <p style="color: #475569; font-size: 10px; font-style: italic; margin: 6px 0 0 0;">
                    Past performance does not guarantee future results. Projections are
                    estimates based on historical data and actual results may vary.</p>
            </div>"""


def _build_expense_card_header(
    g: Dict[str, Any], pct: float, bar_color: str, period: str,
    goal_id: int, email_mode: bool, brand_color: str, currency: str,
    inline_images: Optional[List[Tuple[str, bytes]]],
) -> str:
    """Build card header: name, progress bar, trend chart, minimap."""
    bar_width = min(pct, 100)
    track_label = "On Track" if g.get("on_track") else "Behind"
    track_color = "#10b981" if g.get("on_track") else "#f59e0b"

    header_html = f"""
        <div style="margin: 0 0 15px 0; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155; overflow: hidden;">
            <div style="padding: 12px 12px 0 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;
                            margin: 0 0 8px 0;">
                    <span style="color: #f1f5f9; font-weight: 600; font-size: 14px;">
                        {g.get('name', '')}
                        <span style="color: #94a3b8; font-weight: 400; font-size: 12px;
                                     margin-left: 6px;">Expenses / {period.capitalize()}</span>
                    </span>
                    <span style="font-size: 12px; font-weight: 600;">
                        <span style="color: {bar_color};">{_fmt_coverage_pct(pct)} Covered</span>
                        <span style="color: {track_color}; margin-left: 8px;">
                            &bull; {track_label}</span>
                    </span>
                </div>
                <div style="background-color: #334155; border-radius: 4px; height: 8px;
                            overflow: hidden; margin-bottom: 10px;">
                    <div style="background-color: {bar_color}; width: {bar_width}%;
                                height: 100%; border-radius: 4px;"></div>
                </div>
            </div>"""

    trend_data = g.get("trend_data")
    if trend_data:
        from app.services.report_generator_service.html_builder import (
            _build_trend_chart_svg,
        )
        from app.services.report_generator_service.chart_renderer import (
            _render_trend_chart_png,
        )
        if email_mode and inline_images is not None:
            png_bytes = _render_trend_chart_png(trend_data, brand_color, currency)
            if png_bytes:
                cid = f"goal-chart-{goal_id}"
                inline_images.append((cid, png_bytes))
                header_html += (
                    '<div style="padding: 0 12px 10px 12px;">'
                    f'<img src="cid:{cid}" width="660"'
                    ' style="width:100%;height:auto;display:block;'
                    'border-radius:6px;" alt="Expense coverage trend"/>'
                    '</div>'
                )
        else:
            svg_html = _build_trend_chart_svg(trend_data, brand_color, currency)
            header_html += (
                f'<div style="padding: 0 12px 10px 12px;">'
                f'{svg_html}</div>'
            )

    chart_settings = g.get("chart_settings", {})
    if chart_settings.get("show_minimap") and trend_data:
        try:
            from app.services.report_generator_service.html_builder import (
                _build_minimap_svg,
            )
            minimap_html = _build_minimap_svg(
                full_data_points=chart_settings.get("full_data_points", []),
                horizon_date=chart_settings.get("horizon_date", ""),
                target_date=chart_settings["target_date"],
                brand_color=brand_color,
                currency=currency,
            )
            header_html += minimap_html
        except (KeyError, ValueError):
            pass

    return header_html


def _build_expenses_goal_card(
    g: Dict[str, Any], email_mode: bool = False,
    schedule_meta: Optional[Dict[str, Any]] = None,
    brand_color: str = "#3b82f6",
    inline_images: Optional[List[Tuple[str, bytes]]] = None,
) -> str:
    """Expenses goal card with Coverage + Upcoming tabs."""
    coverage = g.get("expense_coverage", {})
    pct = coverage.get("coverage_pct", 0)
    bar_color = "#10b981" if pct >= 100 else "#f59e0b" if pct >= 50 else "#ef4444"
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    prefix = "" if currency == "BTC" else "$"
    period = g.get("expense_period", "monthly")
    tax_pct = g.get("tax_withholding_pct", 0)
    goal_id = g.get("goal_id") or g.get("id") or 0
    items = coverage.get("items", [])
    savings_targets = coverage.get("savings_targets", [])
    total_exp = coverage.get("total_expenses", 0)

    coverage_content = _build_expense_coverage_html(
        g, coverage, items, prefix, fmt, currency, period, tax_pct, savings_targets,
    )
    upcoming_content = _build_expense_upcoming_html(
        items, prefix, fmt, schedule_meta,
    )
    projection_content = _build_expense_projection_html(
        g, prefix, fmt, currency, period, total_exp, tax_pct,
    )
    header_html = _build_expense_card_header(
        g, pct, bar_color, period, goal_id, email_mode,
        brand_color, currency, inline_images,
    )

    if email_mode:
        section_hdr = (
            'style="color: #3b82f6; font-size: 12px; font-weight: 600;'
            ' padding: 8px 12px; margin: 0; border-bottom: 1px solid #334155;'
            ' background-color: #162032;"'
        )
        proj_block = ""
        if projection_content:
            proj_block = (
                f'<p {section_hdr}>Projections</p>'
                f'<div style="padding: 12px;">{projection_content}</div>'
            )
        return (
            f"{header_html}"
            f'<p {section_hdr}>Coverage</p>'
            f'<div style="padding: 12px;">{coverage_content}</div>'
            f'<p {section_hdr}>Upcoming</p>'
            f'<div style="padding: 12px;">{upcoming_content}</div>'
            f'{proj_block}'
            f'</div>'
        )

    return _build_expense_card_css_tabs(
        header_html, coverage_content, upcoming_content,
        projection_content, goal_id,
    )


def _build_expense_card_css_tabs(
    header_html: str, coverage_content: str, upcoming_content: str,
    projection_content: str, goal_id: int,
) -> str:
    """Assemble the in-app CSS-only tabbed card layout."""
    tab_name = f"exp-tab-{goal_id}"
    cov_id = f"exp-tab-coverage-{goal_id}"
    upc_id = f"exp-tab-upcoming-{goal_id}"
    proj_id = f"exp-tab-proj-{goal_id}"
    cov_panel = f"exp-panel-coverage-{goal_id}"
    upc_panel = f"exp-panel-upcoming-{goal_id}"
    proj_panel = f"exp-panel-proj-{goal_id}"

    proj_css = ""
    if projection_content:
        proj_css = f"""
        #{proj_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{proj_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{proj_id}:checked ~ #{proj_panel}
            {{ display: block !important; }}"""

    css_rules = f"""
        #{cov_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{cov_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{cov_id}:checked ~ #{cov_panel}
            {{ display: block !important; }}
        #{upc_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{upc_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{upc_id}:checked ~ #{upc_panel}
            {{ display: block !important; }}{proj_css}
    """

    tab_label_style = (
        'padding: 8px 14px; cursor: pointer; font-size: 12px; font-weight: 600;'
        ' font-family: inherit; border-bottom: 2px solid transparent;'
        ' color: #64748b; transition: all 0.2s;'
    )

    proj_radio = ""
    proj_label = ""
    proj_panel_html = ""
    if projection_content:
        proj_radio = (
            f'<input type="radio" name="{tab_name}" id="{proj_id}" style="display:none">'
        )
        proj_label = f'<label for="{proj_id}" style="{tab_label_style}">Projections</label>'
        proj_panel_html = (
            f'<div id="{proj_panel}" style="display: none; padding: 12px;">'
            f'{projection_content}</div>'
        )

    return f"""
        <style>{css_rules}</style>
        {header_html}
            <input type="radio" name="{tab_name}" id="{cov_id}" style="display:none" checked>
            <input type="radio" name="{tab_name}" id="{upc_id}" style="display:none">
            {proj_radio}
            <div class="exp-tab-bar-{goal_id}" style="display: flex;
                        border-bottom: 1px solid #334155; background-color: #162032;">
                <label for="{cov_id}" style="{tab_label_style}">Coverage</label>
                <label for="{upc_id}" style="{tab_label_style}">Upcoming</label>
                {proj_label}
            </div>
            <div id="{cov_panel}" style="display: none; padding: 12px;">
                {coverage_content}
            </div>
            <div id="{upc_panel}" style="display: none; padding: 12px;">
                {upcoming_content}
            </div>
            {proj_panel_html}
        </div>"""
