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
