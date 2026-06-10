"""
Expense Sections — HTML section builders (coverage, changes, savings, etc).

Part of the report_generator_service package.
"""

from datetime import datetime
from app.utils.timeutil import utcnow
from typing import Any, Dict, Optional

from app.services.report_generator_service.expense_schedule import (
    _MONTH_ABBREVS,
    _fmt_coverage_pct,
    _format_due_label,
    _get_lookahead_items,
    _get_upcoming_items,
    _ordinal_day,
)


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
    now = utcnow()
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
