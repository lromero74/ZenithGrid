"""
Email Service - Send transactional emails via Amazon SES

Uses boto3 SDK (HTTPS API calls, no SMTP needed).
Auth via EC2 instance IAM role — no API keys to manage.
Brand values (name, tagline, copyright) loaded from brand_service.
"""

import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.services.brand_service import get_brand

logger = logging.getLogger(__name__)


def _get_ses_client():
    """Get SES client using IAM instance role credentials."""
    return boto3.client("ses", region_name=settings.ses_region)


def _brand():
    """Shortcut to get cached brand config."""
    return get_brand()


def _email_header() -> str:
    """Common HTML email header with brand name + tagline."""
    b = _brand()
    return (
        '<div style="text-align: center; padding: 20px 0;'
        ' border-bottom: 1px solid #334155;">'
        f'<h1 style="color: #3b82f6; margin: 0; font-size: 24px;">'
        f'{b["shortName"]}</h1>'
        f'<p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 14px;">'
        f'{b["tagline"]}</p>'
        '</div>'
    )


def _email_footer() -> str:
    """Common HTML email footer with copyright."""
    b = _brand()
    return (
        '<div style="border-top: 1px solid #334155;'
        ' padding: 15px 0; text-align: center;">'
        '<p style="color: #64748b; font-size: 12px; margin: 0;">'
        f'&copy; {b["copyright"]}</p>'
        '</div>'
    )


def send_verification_email(
    to: str, verification_url: str, display_name: str,
    verification_code: str = ""
) -> bool:
    """Send email verification link + code to new user."""
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping verification email to %s", to)
        return False

    b = _brand()
    name = display_name or to
    subject = f"Verify your email - {b['shortName']}"

    code_section = ""
    code_text = ""
    if verification_code:
        code_section = (
            '<div style="text-align: center; padding: 20px 0; margin: 15px 0;'
            ' background-color: #1e293b; border-radius: 8px;'
            ' border: 1px solid #334155;">'
            '<p style="color: #94a3b8; font-size: 13px;'
            ' margin: 0 0 8px 0;">Or enter this verification code:</p>'
            '<p style="color: #f1f5f9; font-size: 32px; font-weight: 700;'
            ' letter-spacing: 8px; margin: 0; font-family: monospace;">'
            f'{verification_code}</p>'
            '</div>'
        )
        code_text = f"\nOr enter this verification code: {verification_code}\n"

    html_body = (
        '<div style="font-family: -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, sans-serif; max-width: 600px;"
        ' margin: 0 auto; padding: 20px;'
        ' background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 30px 0;">'
        f'<h2 style="color: #f1f5f9; margin: 0 0 15px 0;">Welcome, {name}!</h2>'
        '<p style="color: #cbd5e1; line-height: 1.6;">'
        'Thanks for creating an account.'
        ' Please verify your email address to get started.</p>'
        '<div style="text-align: center; padding: 25px 0;">'
        f'<a href="{verification_url}" style="display: inline-block;'
        ' background-color: #3b82f6; color: #ffffff;'
        ' text-decoration: none; padding: 14px 32px;'
        ' border-radius: 8px; font-weight: 600; font-size: 16px;">'
        'Verify Email Address</a></div>'
        f'{code_section}'
        '<p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">'
        "This link and code expire in 24 hours."
        " If you didn't create this account,"
        ' you can safely ignore this email.</p>'
        '<p style="color: #64748b; font-size: 12px;'
        ' margin-top: 20px; word-break: break-all;">'
        f'Or copy this link: {verification_url}</p>'
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )
    text_body = (
        f"Welcome to {b['shortName']}, {name}!\n\n"
        f"Please verify your email by visiting:\n{verification_url}\n"
        f"{code_text}\n"
        "This link and code expire in 24 hours.\n"
        "If you didn't create this account, ignore this email."
    )

    return _send_email(to, subject, html_body, text_body)


def send_password_reset_email(to: str, reset_url: str, display_name: str) -> bool:
    """Send password reset link."""
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping password reset email to %s", to)
        return False

    b = _brand()
    name = display_name or to
    subject = f"Reset your password - {b['shortName']}"
    html_body = (
        '<div style="font-family: -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, sans-serif; max-width: 600px;"
        ' margin: 0 auto; padding: 20px;'
        ' background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 30px 0;">'
        '<h2 style="color: #f1f5f9; margin: 0 0 15px 0;">Password Reset</h2>'
        '<p style="color: #cbd5e1; line-height: 1.6;">'
        f'Hi {name}, we received a request to reset your password.'
        ' Click the button below to choose a new one.</p>'
        '<div style="text-align: center; padding: 25px 0;">'
        f'<a href="{reset_url}" style="display: inline-block;'
        ' background-color: #3b82f6; color: #ffffff;'
        ' text-decoration: none; padding: 14px 32px;'
        ' border-radius: 8px; font-weight: 600; font-size: 16px;">'
        'Reset Password</a></div>'
        '<p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">'
        "This link expires in 1 hour."
        " If you didn't request a password reset,"
        ' you can safely ignore this email.</p>'
        '<p style="color: #64748b; font-size: 12px;'
        ' margin-top: 20px; word-break: break-all;">'
        f'Or copy this link: {reset_url}</p>'
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )
    text_body = (
        f"Hi {name},\n\n"
        f"We received a request to reset your password.\n"
        f"Visit this link to set a new password:\n{reset_url}\n\n"
        "This link expires in 1 hour.\n"
        "If you didn't request this, ignore this email."
    )

    return _send_email(to, subject, html_body, text_body)


def send_mfa_verification_email(
    to: str, code: str, link_url: str, display_name: str
) -> bool:
    """Send MFA verification email with 6-digit code and clickable link."""
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping MFA verification email to %s", to)
        return False

    b = _brand()
    name = display_name or to
    subject = f"Login verification code - {b['shortName']}"

    html_body = (
        '<div style="font-family: -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, sans-serif; max-width: 600px;"
        ' margin: 0 auto; padding: 20px;'
        ' background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 30px 0;">'
        '<h2 style="color: #f1f5f9; margin: 0 0 15px 0;">'
        'Login Verification</h2>'
        '<p style="color: #cbd5e1; line-height: 1.6;">'
        f'Hi {name}, a login attempt was made on your account.'
        ' Use the code below or click the button'
        ' to verify your identity.</p>'
        '<div style="text-align: center; padding: 20px 0; margin: 15px 0;'
        ' background-color: #1e293b; border-radius: 8px;'
        ' border: 1px solid #334155;">'
        '<p style="color: #94a3b8; font-size: 13px;'
        ' margin: 0 0 8px 0;">Your verification code:</p>'
        '<p style="color: #f1f5f9; font-size: 32px; font-weight: 700;'
        f' letter-spacing: 8px; margin: 0; font-family: monospace;">'
        f'{code}</p></div>'
        '<div style="text-align: center; padding: 20px 0;">'
        f'<a href="{link_url}" style="display: inline-block;'
        ' background-color: #3b82f6; color: #ffffff;'
        ' text-decoration: none; padding: 14px 32px;'
        ' border-radius: 8px; font-weight: 600; font-size: 16px;">'
        'Verify Login</a></div>'
        '<p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">'
        'This code and link expire in 5 minutes.'
        " If you didn't attempt to log in,"
        ' please change your password immediately.</p>'
        '<p style="color: #64748b; font-size: 12px;'
        ' margin-top: 20px; word-break: break-all;">'
        f'Or copy this link: {link_url}</p>'
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )
    text_body = (
        f"Hi {name},\n\n"
        f"A login attempt was made on your {b['shortName']} account.\n\n"
        f"Your verification code: {code}\n\n"
        f"Or click this link to verify: {link_url}\n\n"
        "This code and link expire in 5 minutes.\n"
        "If you didn't attempt to log in,"
        " please change your password immediately."
    )

    return _send_email(to, subject, html_body, text_body)


def send_report_email(
    to: str,
    cc: list,
    subject: str,
    html_body: str,
    text_body: str,
    pdf_attachment: bytes = None,
    pdf_filename: str = "report.pdf",
    inline_images: list = None,
) -> bool:
    """
    Send a report email with optional PDF attachment, CC recipients,
    and CID-embedded inline images.

    Uses SES send_raw_email for MIME multipart support.
    """
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping report email to %s", to)
        return False

    from email.mime.application import MIMEApplication
    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = settings.ses_sender_email
        msg["To"] = to
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Build the body (HTML + text alternative)
        # When inline images are present, wrap HTML in multipart/related
        # so CID references resolve correctly.
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(text_body, "plain", "utf-8"))

        if inline_images:
            related_part = MIMEMultipart("related")
            related_part.attach(MIMEText(html_body, "html", "utf-8"))
            for cid, png_bytes in inline_images:
                img_part = MIMEImage(png_bytes, "png")
                img_part.add_header("Content-ID", f"<{cid}>")
                img_part.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
                related_part.attach(img_part)
            body_part.attach(related_part)
        else:
            body_part.attach(MIMEText(html_body, "html", "utf-8"))

        msg.attach(body_part)

        # Attach PDF if provided
        if pdf_attachment:
            pdf_part = MIMEApplication(pdf_attachment, "pdf")
            pdf_part.add_header(
                "Content-Disposition", "attachment", filename=pdf_filename
            )
            msg.attach(pdf_part)

        # All recipients (To + Cc)
        all_recipients = [to] + (cc or [])

        client = _get_ses_client()
        response = client.send_raw_email(
            Source=settings.ses_sender_email,
            Destinations=all_recipients,
            RawMessage={"Data": msg.as_string()},
        )
        message_id = response.get("MessageId", "unknown")
        logger.info(
            "Report email sent to %s (cc: %s, MessageId: %s)",
            to, cc, message_id,
        )
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        logger.error(
            "SES error sending report to %s: %s - %s", to, error_code, error_msg
        )
        return False
    except Exception as e:
        logger.error("Failed to send report email to %s: %s", to, e)
        return False


def send_invitation_email(
    to: str,
    accept_url: str,
    inviter_name: str,
    role: str,
    account_name: str,
) -> bool:
    """
    Send an account sharing invitation email.

    The link is one-time, expires in 7 days, and requires authentication
    as the invited email address before it can be accepted.
    """
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping invitation email to %s", to)
        return False

    b = _brand()
    role_label = "Manager" if role == "manager" else "Observer"
    role_description = (
        "manage bots, view positions, and run reports"
        if role == "manager"
        else "view account activity in read-only mode"
    )
    subject = f"{inviter_name} invited you to co-manage {account_name} on {b['shortName']}"

    html_body = (
        '<div style="font-family: -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, sans-serif; max-width: 600px;"
        ' margin: 0 auto; padding: 20px; background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 30px 0;">'
        f'<h2 style="color: #f1f5f9; margin: 0 0 15px 0;">'
        f"You've been invited as {role_label}</h2>"
        '<p style="color: #cbd5e1; line-height: 1.6;">'
        f'<strong style="color: #f1f5f9;">{inviter_name}</strong> has invited you to '
        f'{role_description} on their account '
        f'<strong style="color: #f1f5f9;">{account_name}</strong>.</p>'
        '<div style="background-color: #1e293b; border-radius: 8px;'
        ' border: 1px solid #334155; padding: 16px; margin: 20px 0;">'
        f'<p style="color: #94a3b8; margin: 0 0 4px 0; font-size: 12px;">ROLE</p>'
        f'<p style="color: #3b82f6; margin: 0; font-size: 18px; font-weight: 600;">'
        f'{role_label}</p>'
        '</div>'
        '<div style="text-align: center; padding: 25px 0;">'
        f'<a href="{accept_url}" style="display: inline-block;'
        ' background-color: #3b82f6; color: #ffffff; text-decoration: none;'
        ' padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">'
        'View Invitation &rarr;</a></div>'
        '<p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">'
        'You must be logged in as the account that received this invitation to accept it. '
        'This link expires in 7 days and can only be used once. '
        "If you were not expecting this invitation, you can safely ignore this email.</p>"
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )

    text_body = (
        f"{inviter_name} has invited you to {role_description} on {account_name} "
        f"({b['shortName']}) as {role_label}.\n\n"
        f"View invitation: {accept_url}\n\n"
        "You must log in as the invited email address to accept. "
        "This link expires in 7 days and can only be used once."
    )

    return _send_email(to, subject, html_body, text_body)


def build_speculative_calibration_text_body(
    *,
    analysis: dict,
    user_first_name: str,
    user_id: int,
    dismiss_url: str,
) -> str:
    """Render the plain-text body for the speculative calibration alert.

    The COPY EVERYTHING BELOW/ABOVE markers and the numbered step list are
    verbatim per PRPs/high-risk-doubling-preset.md §Phase F Task F4 — the
    body is designed so a fresh Claude Code session can recalibrate the
    weights in speculative_signals.py with no prior context. Do not
    reword without reading the PRP.
    """
    components = sorted(
        analysis.get("components", []),
        key=lambda c: c.get("win_rate_pct", 0),
        reverse=True,
    )
    component_lines = "\n".join(
        f"  {c['name']:<24} {c['fires']:>4} fires    {c['win_rate_pct']:>5.1f}%"
        for c in components
    )

    pnl = float(analysis.get("overall_realized_pnl_usd", 0.0))
    win_rate = analysis.get("overall_win_rate_pct", 0.0)
    total_closed = analysis.get("total_closed", 0)
    wins = analysis.get("wins", 0)
    losses = analysis.get("losses", 0)
    top = analysis.get("top_component", "")
    top_rate = analysis.get("top_win_rate_pct", 0.0)
    bottom = analysis.get("bottom_component", "")
    bottom_rate = analysis.get("bottom_win_rate_pct", 0.0)
    divergence = float(analysis.get("divergence_pp", 0.0))

    bar = "━" * 44
    return (
        f"Hi {user_first_name},\n\n"
        "Your speculative bot preset has accumulated enough closed positions that\n"
        "it's worth revisiting the signal weights. The signal weights in\n"
        "speculative_signals.py were educated guesses at ship time; this alert\n"
        "fires once we have enough data to calibrate them against real outcomes.\n\n"
        f"{bar}\n"
        "SUMMARY\n"
        f"{bar}\n\n"
        f"Total closed speculative positions:   {total_closed}\n"
        f"Overall win rate:                     {win_rate}%  ({wins}W / {losses}L)\n"
        f"Overall realized PnL:                 ${pnl:+.2f}\n\n"
        f"{bar}\n"
        "COMPONENT PERFORMANCE (fires / win rate)\n"
        f"{bar}\n\n"
        f"{component_lines}\n\n"
        f"Gap between top ({top}) and bottom ({bottom}):\n"
        f"  {divergence:.1f} percentage points\n\n"
        f"{bar}\n"
        "TO ACT ON THIS\n"
        f"{bar}\n\n"
        "Open a new Claude Code session at /home/ec2-user/ZenithGrid and\n"
        "paste the block below. It is self-contained — Claude will have\n"
        "no memory of the original preset design, but this prompt has\n"
        "everything needed to recalibrate.\n\n"
        "━━━━━ COPY EVERYTHING BELOW THIS LINE ━━━━━\n\n"
        "I received a speculative preset calibration alert from ZenithGrid.\n"
        "I want to review and adjust the signal weights in\n"
        "`backend/app/indicators/speculative_signals.py` based on accumulated\n"
        "outcome data in `ai_opinion_log`.\n\n"
        "Reference: `PRPs/high-risk-doubling-preset.md` (Phase F — Calibration\n"
        "Alert Monitor). The monitor fires when ≥50 closed speculative positions\n"
        "have accumulated and component win rates diverge by ≥20 percentage\n"
        "points.\n\n"
        "Current snapshot from the alert:\n"
        f"- Total closed speculative positions: {total_closed}\n"
        f"- Overall win rate: {win_rate}%\n"
        f"- Top component: {top} ({top_rate}% win rate)\n"
        f"- Bottom component: {bottom} ({bottom_rate}% win rate)\n"
        f"- Divergence: {divergence:.1f} percentage points\n\n"
        "Please do this, in order:\n\n"
        "1. Re-verify the numbers in the alert by querying `ai_opinion_log`\n"
        "   joined to `trading.positions` for my user_id\n"
        f"   (user_id={user_id}), filtered to:\n"
        "     - speculative-tagged bots (bot.strategy_config->>'is_speculative' = 'true')\n"
        "     - closed positions (positions.status = 'closed')\n"
        "     - non-null doubling_probability_score\n"
        "   For each weight component in `speculative_signals.py::WEIGHTS`, compute\n"
        "   fire_count (how often it contributed to the score) and win_rate\n"
        "   (wins = position.profit_percentage > 0).\n\n"
        "2. Propose weight adjustments to the `WEIGHTS` dict in\n"
        "   `backend/app/indicators/speculative_signals.py`:\n"
        "     - Lower weights of components whose win rate is materially below\n"
        "       the overall win rate (>5pp below).\n"
        "     - Raise weights of top performers (>5pp above overall win rate).\n"
        "     - Preserve the invariant that weights sum to 100.\n"
        "     - Do NOT change the scorer logic, the prefilter, or the LLM prompt\n"
        "       — only the weights dict.\n\n"
        "3. Show me a before/after weights diff and a one-line reason per change.\n\n"
        "4. Add or update a test in\n"
        "   `backend/tests/indicators/test_speculative_signals.py` that asserts\n"
        "   the new weights sum to 100 and that at least one weight changed.\n\n"
        "5. Write a CHANGELOG entry under the next patch version.\n\n"
        "6. Stop after the weights change and tests pass — do not ship (no\n"
        "   tag, no push, no deploy). I want to review before `/shipit`.\n\n"
        "If the query shows the alert was noisy (no real divergence, or\n"
        "sample size was lower than I claimed), say so and recommend\n"
        "dismissing the alert instead of adjusting weights.\n\n"
        "━━━━━ COPY EVERYTHING ABOVE THIS LINE ━━━━━\n\n"
        "If you want to silence this alert without acting on it, reply to\n"
        f"this email with \"dismiss\" (or click: {dismiss_url}) — the cooldown\n"
        "will reset to 30 days.\n\n"
        "— ZenithGrid\n"
    )


def _build_speculative_calibration_html_body(
    *,
    analysis: dict,
    user_first_name: str,
    user_id: int,
    dismiss_url: str,
) -> str:
    """Wrap the plain-text body in a minimal HTML shell.

    Uses a <pre> block so the COPY EVERYTHING markers and the numbered
    steps render as a single copy-friendly fixed-width region — the
    user-facing point of this email is that the body can be pasted
    whole into a Claude Code session.
    """
    text_body = build_speculative_calibration_text_body(
        analysis=analysis, user_first_name=user_first_name,
        user_id=user_id, dismiss_url=dismiss_url,
    )
    import html as _html
    escaped = _html.escape(text_body)
    # Preserve the dismiss link as an actual clickable anchor.
    escaped = escaped.replace(
        _html.escape(dismiss_url),
        f'<a href="{_html.escape(dismiss_url)}" '
        'style="color: #3b82f6;">'
        f'{_html.escape(dismiss_url)}</a>',
    )
    return (
        '<div style="font-family: -apple-system, BlinkMacSystemFont,'
        " 'Segoe UI', Roboto, sans-serif; max-width: 720px;"
        ' margin: 0 auto; padding: 20px;'
        ' background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 20px 0;">'
        '<pre style="font-family: Menlo, Consolas, monospace;'
        ' font-size: 13px; line-height: 1.5; color: #e2e8f0;'
        ' white-space: pre-wrap; word-break: break-word;">'
        f'{escaped}'
        '</pre>'
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )


def send_speculative_calibration_email(
    *,
    to: str,
    analysis: dict,
    user_first_name: str,
    user_id: int,
    dismiss_url: str,
) -> bool:
    """Send the calibration alert email.

    `analysis` is the dict returned by
    app.services.speculative_bucket_service.analyze_speculative_calibration.
    """
    if not settings.ses_enabled:
        logger.warning(
            "SES disabled, skipping speculative calibration email to %s", to,
        )
        return False

    b = _brand()
    subject = f"{b['shortName']} — Time to review speculative preset weights"
    text_body = build_speculative_calibration_text_body(
        analysis=analysis, user_first_name=user_first_name,
        user_id=user_id, dismiss_url=dismiss_url,
    )
    html_body = _build_speculative_calibration_html_body(
        analysis=analysis, user_first_name=user_first_name,
        user_id=user_id, dismiss_url=dismiss_url,
    )
    return _send_email(to, subject, html_body, text_body)


def _send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SES. Returns True on success."""
    try:
        client = _get_ses_client()
        response = client.send_email(
            Source=settings.ses_sender_email,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        )
        message_id = response.get("MessageId", "unknown")
        logger.info("Email sent to %s (MessageId: %s)", to, message_id)
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        logger.error(
            "SES error sending to %s: %s - %s", to, error_code, error_msg
        )
        return False
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False
