"""
Tests for backend/app/services/email_service.py

Covers: send_verification_email, send_password_reset_email,
        send_mfa_verification_email, send_report_email,
        _send_email, _email_header, _email_footer, _get_ses_client
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


# ── Shared brand stub ────────────────────────────────────────────────────────

FAKE_BRAND = {
    "shortName": "TestBot",
    "tagline": "Test Trading Platform",
    "copyright": "2026 TestCorp",
}


@pytest.fixture(autouse=True)
def _mock_brand():
    """Patch brand_service.get_brand for all tests in this module."""
    with patch(
        "app.services.email_service.get_brand", return_value=FAKE_BRAND
    ):
        yield


@pytest.fixture
def mock_ses_client():
    """Create a mock SES client that returns a successful response."""
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "test-msg-id-123"}
    client.send_raw_email.return_value = {"MessageId": "test-raw-msg-456"}
    return client


@pytest.fixture
def patch_ses(mock_ses_client):
    """Patch _get_ses_client to return the mock SES client."""
    with patch(
        "app.services.email_service._get_ses_client",
        return_value=mock_ses_client,
    ):
        yield mock_ses_client


@pytest.fixture
def ses_enabled():
    """Ensure SES is enabled for tests that need it."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.ses_enabled = True
        mock_settings.ses_region = "us-east-1"
        mock_settings.ses_sender_email = "noreply@test.com"
        yield mock_settings


@pytest.fixture
def ses_disabled():
    """SES disabled fixture."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.ses_enabled = False
        mock_settings.ses_region = "us-east-1"
        mock_settings.ses_sender_email = "noreply@test.com"
        yield mock_settings


# ── _get_ses_client ──────────────────────────────────────────────────────────


class TestGetSesClient:
    """Tests for _get_ses_client()"""

    def test_creates_boto3_ses_client_with_configured_region(self, ses_enabled):
        """Happy path: creates boto3 SES client with the configured region."""
        from app.services.email_service import _get_ses_client

        with patch("app.services.email_service.boto3") as mock_boto3:
            _get_ses_client()
            mock_boto3.client.assert_called_once_with(
                "ses", region_name="us-east-1"
            )


# ── _email_header / _email_footer ───────────────────────────────────────────


class TestEmailHeader:
    """Tests for _email_header()"""

    def test_header_contains_brand_short_name(self):
        """Happy path: header HTML includes the brand short name."""
        from app.services.email_service import _email_header

        html = _email_header()
        assert "TestBot" in html

    def test_header_contains_brand_tagline(self):
        """Happy path: header HTML includes the brand tagline."""
        from app.services.email_service import _email_header

        html = _email_header()
        assert "Test Trading Platform" in html

    def test_header_returns_valid_html_div(self):
        """Edge case: header starts and ends with div tags."""
        from app.services.email_service import _email_header

        html = _email_header()
        assert html.startswith("<div")
        assert html.endswith("</div>")


class TestEmailFooter:
    """Tests for _email_footer()"""

    def test_footer_contains_copyright(self):
        """Happy path: footer HTML includes the copyright text."""
        from app.services.email_service import _email_footer

        html = _email_footer()
        assert "2026 TestCorp" in html

    def test_footer_returns_valid_html_div(self):
        """Edge case: footer starts and ends with div tags."""
        from app.services.email_service import _email_footer

        html = _email_footer()
        assert html.startswith("<div")
        assert html.endswith("</div>")


# ── _send_email (internal helper) ───────────────────────────────────────────


class TestSendEmail:
    """Tests for _send_email()"""

    def test_send_email_success_returns_true(self, ses_enabled, patch_ses):
        """Happy path: successful SES send returns True."""
        from app.services.email_service import _send_email

        result = _send_email(
            "user@example.com", "Test Subject", "<p>HTML</p>", "Text"
        )
        assert result is True

    def test_send_email_calls_ses_with_correct_params(
        self, ses_enabled, patch_ses
    ):
        """Happy path: SES send_email receives correct arguments."""
        from app.services.email_service import _send_email

        _send_email(
            "user@example.com", "Test Subject", "<p>HTML</p>", "Plain text"
        )
        patch_ses.send_email.assert_called_once()
        call_kwargs = patch_ses.send_email.call_args[1]
        assert call_kwargs["Source"] == "noreply@test.com"
        assert call_kwargs["Destination"] == {
            "ToAddresses": ["user@example.com"]
        }
        assert call_kwargs["Message"]["Subject"]["Data"] == "Test Subject"
        assert call_kwargs["Message"]["Body"]["Html"]["Data"] == "<p>HTML</p>"
        assert (
            call_kwargs["Message"]["Body"]["Text"]["Data"] == "Plain text"
        )

    def test_send_email_client_error_returns_false(
        self, ses_enabled, patch_ses
    ):
        """Failure: SES ClientError returns False, doesn't raise."""
        from app.services.email_service import _send_email

        patch_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Bad address"}},
            "SendEmail",
        )
        result = _send_email(
            "bad@example.com", "Subject", "<p>HTML</p>", "Text"
        )
        assert result is False

    def test_send_email_unexpected_exception_returns_false(
        self, ses_enabled, patch_ses
    ):
        """Failure: unexpected exception returns False, doesn't raise."""
        from app.services.email_service import _send_email

        patch_ses.send_email.side_effect = RuntimeError("Connection lost")
        result = _send_email(
            "user@example.com", "Subject", "<p>HTML</p>", "Text"
        )
        assert result is False


# ── send_verification_email ──────────────────────────────────────────────────


class TestSendVerificationEmail:
    """Tests for send_verification_email()"""

    def test_verification_email_success(self, ses_enabled, patch_ses):
        """Happy path: sends verification email and returns True."""
        from app.services.email_service import send_verification_email

        result = send_verification_email(
            "new@example.com",
            "https://example.com/verify?token=abc",
            "Alice",
        )
        assert result is True
        patch_ses.send_email.assert_called_once()

    def test_verification_email_contains_url_in_body(
        self, ses_enabled, patch_ses
    ):
        """Happy path: email body contains the verification URL."""
        from app.services.email_service import send_verification_email

        send_verification_email(
            "new@example.com",
            "https://example.com/verify?token=abc",
            "Alice",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        text = call_kwargs["Message"]["Body"]["Text"]["Data"]
        assert "https://example.com/verify?token=abc" in html
        assert "https://example.com/verify?token=abc" in text

    def test_verification_email_includes_code_when_provided(
        self, ses_enabled, patch_ses
    ):
        """Edge case: verification code section appears when code is given."""
        from app.services.email_service import send_verification_email

        send_verification_email(
            "new@example.com",
            "https://example.com/verify",
            "Alice",
            verification_code="123456",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        text = call_kwargs["Message"]["Body"]["Text"]["Data"]
        assert "123456" in html
        assert "123456" in text

    def test_verification_email_no_code_section_when_empty(
        self, ses_enabled, patch_ses
    ):
        """Edge case: no verification code section when code is empty."""
        from app.services.email_service import send_verification_email

        send_verification_email(
            "new@example.com",
            "https://example.com/verify",
            "Alice",
            verification_code="",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "verification code" not in html.lower()

    def test_verification_email_uses_email_as_name_when_empty(
        self, ses_enabled, patch_ses
    ):
        """Edge case: falls back to email address when display_name is empty."""
        from app.services.email_service import send_verification_email

        send_verification_email(
            "fallback@example.com",
            "https://example.com/verify",
            "",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "fallback@example.com" in html

    def test_verification_email_subject_contains_brand(
        self, ses_enabled, patch_ses
    ):
        """Happy path: subject line includes the brand short name."""
        from app.services.email_service import send_verification_email

        send_verification_email(
            "user@example.com", "https://example.com/verify", "Alice"
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        subject = call_kwargs["Message"]["Subject"]["Data"]
        assert "TestBot" in subject
        assert "Verify" in subject

    def test_verification_email_ses_disabled_returns_false(
        self, ses_disabled
    ):
        """Failure: returns False when SES is disabled."""
        from app.services.email_service import send_verification_email

        result = send_verification_email(
            "user@example.com", "https://example.com/verify", "Alice"
        )
        assert result is False


# ── send_password_reset_email ────────────────────────────────────────────────


class TestSendPasswordResetEmail:
    """Tests for send_password_reset_email()"""

    def test_password_reset_success(self, ses_enabled, patch_ses):
        """Happy path: sends password reset email and returns True."""
        from app.services.email_service import send_password_reset_email

        result = send_password_reset_email(
            "user@example.com",
            "https://example.com/reset?token=xyz",
            "Bob",
        )
        assert result is True
        patch_ses.send_email.assert_called_once()

    def test_password_reset_body_contains_reset_url(
        self, ses_enabled, patch_ses
    ):
        """Happy path: email body contains the reset URL."""
        from app.services.email_service import send_password_reset_email

        send_password_reset_email(
            "user@example.com",
            "https://example.com/reset?token=xyz",
            "Bob",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        text = call_kwargs["Message"]["Body"]["Text"]["Data"]
        assert "https://example.com/reset?token=xyz" in html
        assert "https://example.com/reset?token=xyz" in text

    def test_password_reset_uses_email_when_name_empty(
        self, ses_enabled, patch_ses
    ):
        """Edge case: uses email address when display_name is empty."""
        from app.services.email_service import send_password_reset_email

        send_password_reset_email(
            "noname@example.com",
            "https://example.com/reset",
            "",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "noname@example.com" in html

    def test_password_reset_subject_contains_brand(
        self, ses_enabled, patch_ses
    ):
        """Happy path: subject mentions brand and password reset."""
        from app.services.email_service import send_password_reset_email

        send_password_reset_email(
            "user@example.com", "https://example.com/reset", "Bob"
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        subject = call_kwargs["Message"]["Subject"]["Data"]
        assert "TestBot" in subject
        assert "password" in subject.lower()

    def test_password_reset_ses_disabled_returns_false(self, ses_disabled):
        """Failure: returns False when SES is disabled."""
        from app.services.email_service import send_password_reset_email

        result = send_password_reset_email(
            "user@example.com", "https://example.com/reset", "Bob"
        )
        assert result is False

    def test_password_reset_ses_error_returns_false(
        self, ses_enabled, patch_ses
    ):
        """Failure: SES error returns False."""
        from app.services.email_service import send_password_reset_email

        patch_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}},
            "SendEmail",
        )
        result = send_password_reset_email(
            "user@example.com", "https://example.com/reset", "Bob"
        )
        assert result is False


# ── send_mfa_verification_email ──────────────────────────────────────────────


class TestSendMfaVerificationEmail:
    """Tests for send_mfa_verification_email()"""

    def test_mfa_email_success(self, ses_enabled, patch_ses):
        """Happy path: sends MFA verification email and returns True."""
        from app.services.email_service import send_mfa_verification_email

        result = send_mfa_verification_email(
            "user@example.com",
            "987654",
            "https://example.com/mfa?token=abc",
            "Charlie",
        )
        assert result is True
        patch_ses.send_email.assert_called_once()

    def test_mfa_email_body_contains_code(self, ses_enabled, patch_ses):
        """Happy path: email body contains the MFA code."""
        from app.services.email_service import send_mfa_verification_email

        send_mfa_verification_email(
            "user@example.com",
            "543210",
            "https://example.com/mfa",
            "Charlie",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        text = call_kwargs["Message"]["Body"]["Text"]["Data"]
        assert "543210" in html
        assert "543210" in text

    def test_mfa_email_body_contains_link(self, ses_enabled, patch_ses):
        """Happy path: email body contains the verification link."""
        from app.services.email_service import send_mfa_verification_email

        send_mfa_verification_email(
            "user@example.com",
            "111222",
            "https://example.com/mfa?token=abc",
            "Charlie",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        text = call_kwargs["Message"]["Body"]["Text"]["Data"]
        assert "https://example.com/mfa?token=abc" in html
        assert "https://example.com/mfa?token=abc" in text

    def test_mfa_email_uses_email_when_name_empty(
        self, ses_enabled, patch_ses
    ):
        """Edge case: uses email address when display_name is empty."""
        from app.services.email_service import send_mfa_verification_email

        send_mfa_verification_email(
            "anon@example.com",
            "000000",
            "https://example.com/mfa",
            "",
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "anon@example.com" in html

    def test_mfa_email_ses_disabled_returns_false(self, ses_disabled):
        """Failure: returns False when SES is disabled."""
        from app.services.email_service import send_mfa_verification_email

        result = send_mfa_verification_email(
            "user@example.com", "123456", "https://example.com/mfa", "Charlie"
        )
        assert result is False

    def test_mfa_email_subject_contains_brand(self, ses_enabled, patch_ses):
        """Happy path: subject mentions brand."""
        from app.services.email_service import send_mfa_verification_email

        send_mfa_verification_email(
            "user@example.com", "123456", "https://example.com/mfa", "Charlie"
        )
        call_kwargs = patch_ses.send_email.call_args[1]
        subject = call_kwargs["Message"]["Subject"]["Data"]
        assert "TestBot" in subject


# ── send_report_email ────────────────────────────────────────────────────────


class TestSendReportEmail:
    """Tests for send_report_email()"""

    def test_report_email_success_without_attachment(
        self, ses_enabled, patch_ses
    ):
        """Happy path: sends report without PDF and returns True."""
        from app.services.email_service import send_report_email

        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Monthly Report",
            html_body="<h1>Report</h1>",
            text_body="Report text",
        )
        assert result is True
        patch_ses.send_raw_email.assert_called_once()

    def test_report_email_success_with_pdf_attachment(
        self, ses_enabled, patch_ses
    ):
        """Happy path: sends report with PDF attachment."""
        from app.services.email_service import send_report_email

        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Monthly Report",
            html_body="<h1>Report</h1>",
            text_body="Report text",
            pdf_attachment=b"%PDF-1.4 fake pdf content",
            pdf_filename="report_jan.pdf",
        )
        assert result is True
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        raw_msg = call_kwargs["RawMessage"]["Data"]
        assert "report_jan.pdf" in raw_msg

    def test_report_email_with_cc_recipients(self, ses_enabled, patch_ses):
        """Happy path: includes CC recipients in raw email."""
        from app.services.email_service import send_report_email

        result = send_report_email(
            to="primary@example.com",
            cc=["cc1@example.com", "cc2@example.com"],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        assert result is True
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        destinations = call_kwargs["Destinations"]
        assert "primary@example.com" in destinations
        assert "cc1@example.com" in destinations
        assert "cc2@example.com" in destinations

    def test_report_email_empty_cc_list(self, ses_enabled, patch_ses):
        """Edge case: empty CC list sends only to the To address."""
        from app.services.email_service import send_report_email

        send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        destinations = call_kwargs["Destinations"]
        assert destinations == ["user@example.com"]

    def test_report_email_ses_disabled_returns_false(self, ses_disabled):
        """Failure: returns False when SES is disabled."""
        from app.services.email_service import send_report_email

        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        assert result is False

    def test_report_email_ses_client_error_returns_false(
        self, ses_enabled, patch_ses
    ):
        """Failure: SES ClientError returns False."""
        from app.services.email_service import send_report_email

        patch_ses.send_raw_email.side_effect = ClientError(
            {
                "Error": {
                    "Code": "MessageRejected",
                    "Message": "Email not verified",
                }
            },
            "SendRawEmail",
        )
        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        assert result is False

    def test_report_email_unexpected_error_returns_false(
        self, ses_enabled, patch_ses
    ):
        """Failure: unexpected exception returns False."""
        from app.services.email_service import send_report_email

        patch_ses.send_raw_email.side_effect = RuntimeError("Network error")
        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        assert result is False

    def test_report_email_without_pdf_has_no_attachment_header(
        self, ses_enabled, patch_ses
    ):
        """Edge case: no Content-Disposition attachment when no PDF."""
        from app.services.email_service import send_report_email

        send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>Body</p>",
            text_body="Body",
        )
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        raw_msg = call_kwargs["RawMessage"]["Data"]
        assert "report.pdf" not in raw_msg

    def test_report_email_with_inline_images_embeds_cid(
        self, ses_enabled, patch_ses
    ):
        """Happy path: inline images are CID-embedded in multipart/related."""
        from app.services.email_service import send_report_email

        # Minimal valid 1x1 PNG
        import struct
        import zlib
        png_header = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
        raw_row = b"\x00\xff\x00\x00"
        compressed = zlib.compress(raw_row)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        iend = struct.pack(">I", 0) + b"IEND" + iend_crc
        fake_png = png_header + ihdr + idat + iend

        inline_images = [("goal-chart-42", fake_png)]
        result = send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body='<img src="cid:goal-chart-42">',
            text_body="Report",
            inline_images=inline_images,
        )
        assert result is True
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        raw_msg = call_kwargs["RawMessage"]["Data"]
        assert "goal-chart-42" in raw_msg
        assert "multipart/related" in raw_msg

    def test_report_email_no_inline_images_no_related(
        self, ses_enabled, patch_ses
    ):
        """Edge case: without inline images, no multipart/related wrapper."""
        from app.services.email_service import send_report_email

        send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>No images</p>",
            text_body="Report",
            inline_images=None,
        )
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        raw_msg = call_kwargs["RawMessage"]["Data"]
        assert "multipart/related" not in raw_msg

    def test_report_email_empty_inline_images_no_related(
        self, ses_enabled, patch_ses
    ):
        """Edge case: empty inline_images list behaves like None."""
        from app.services.email_service import send_report_email

        send_report_email(
            to="user@example.com",
            cc=[],
            subject="Report",
            html_body="<p>No images</p>",
            text_body="Report",
            inline_images=[],
        )
        call_kwargs = patch_ses.send_raw_email.call_args[1]
        raw_msg = call_kwargs["RawMessage"]["Data"]
        assert "multipart/related" not in raw_msg
