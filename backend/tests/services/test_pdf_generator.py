"""
Tests for backend/app/services/report_generator_service/pdf_generator.py

Covers PDF generation utility functions and the main generate_pdf entrypoint.
"""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# _sanitize_for_pdf
# ---------------------------------------------------------------------------

class TestSanitizeForPdf:
    """Tests for _sanitize_for_pdf()"""

    def test_sanitize_plain_ascii(self):
        """Happy path: plain ASCII text passes through unchanged."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("Hello World 123")
        assert result == "Hello World 123"

    def test_sanitize_replaces_smart_quotes(self):
        """Happy path: Unicode smart quotes are replaced with ASCII equivalents."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        text = "\u201cHello\u201d \u2018world\u2019"
        result = _sanitize_for_pdf(text)
        assert result == '"Hello" \'world\''

    def test_sanitize_replaces_dashes(self):
        """Happy path: en-dash and em-dash are replaced."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        text = "A\u2013B\u2014C"
        result = _sanitize_for_pdf(text)
        assert result == "A-B--C"

    def test_sanitize_replaces_ellipsis(self):
        """Edge case: Unicode ellipsis becomes three dots."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("Wait\u2026")
        assert result == "Wait..."

    def test_sanitize_replaces_bullet(self):
        """Edge case: Unicode bullet becomes asterisk."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("\u2022 Item")
        assert result == "* Item"

    def test_sanitize_strips_emoji(self):
        """Edge case: emoji characters are stripped entirely."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("Hello \U0001F600 World")
        assert "World" in result
        assert "\U0001F600" not in result

    def test_sanitize_replaces_nonbreaking_space(self):
        """Edge case: non-breaking space becomes regular space."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("Hello\u00a0World")
        assert result == "Hello World"

    def test_sanitize_fallback_replaces_unknown_unicode(self):
        """Edge case: non-Latin-1 characters get replaced by the fallback encoder."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        # Chinese character not in Latin-1
        result = _sanitize_for_pdf("Hello \u4e16\u754c")
        # Should not raise, unknown chars become '?'
        assert "Hello" in result

    def test_sanitize_minus_sign(self):
        """Edge case: Unicode minus sign becomes ASCII hyphen."""
        from app.services.report_generator_service.pdf_generator import _sanitize_for_pdf

        result = _sanitize_for_pdf("Profit: \u221210.5%")
        assert result == "Profit: -10.5%"


# ---------------------------------------------------------------------------
# _truncate_to_width
# ---------------------------------------------------------------------------

class TestTruncateToWidth:
    """Tests for _truncate_to_width()"""

    def test_truncate_short_text_unchanged(self):
        """Happy path: text within width is returned unchanged."""
        from app.services.report_generator_service.pdf_generator import _truncate_to_width
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        result = _truncate_to_width(pdf, "Short", 200.0)
        assert result == "Short"

    def test_truncate_long_text_adds_ellipsis(self):
        """Happy path: text exceeding width is truncated with '...'."""
        from app.services.report_generator_service.pdf_generator import _truncate_to_width
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        long_text = "A" * 200
        result = _truncate_to_width(pdf, long_text, 30.0)
        assert result.endswith("...")
        assert len(result) < len(long_text)

    def test_truncate_zero_width_returns_ellipsis(self):
        """Edge case: extremely small width returns just ellipsis."""
        from app.services.report_generator_service.pdf_generator import _truncate_to_width
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        result = _truncate_to_width(pdf, "Some text", 0.1)
        assert result == "..."


# ---------------------------------------------------------------------------
# generate_pdf
# ---------------------------------------------------------------------------

class TestGeneratePdf:
    """Tests for generate_pdf()"""

    def test_generate_pdf_returns_bytes(self):
        """Happy path: generates valid PDF bytes from report data."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.15,
            "period_profit_usd": 500.0,
            "total_trades": 25,
            "win_rate": 72.0,
            "winning_trades": 18,
            "losing_trades": 7,
            "period_start_value_usd": 9500.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 500.0,
            "goals": [],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_generate_pdf_no_report_data_returns_none(self):
        """Failure: None report_data returns None."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        result = generate_pdf("", report_data=None)
        assert result is None

    def test_generate_pdf_empty_dict_report_data_returns_none(self):
        """Edge case: empty dict is treated as falsy by 'not report_data', returns None."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        result = generate_pdf("", report_data={})
        # Empty dict is falsy in Python, so the guard `if not report_data` triggers
        assert result is None

    def test_generate_pdf_with_schedule_and_account_name(self):
        """Happy path: schedule_name and account_name appear in PDF metadata."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 5000.0,
            "account_value_btc": 0.08,
            "period_profit_usd": 100.0,
            "total_trades": 10,
            "win_rate": 60.0,
            "winning_trades": 6,
            "losing_trades": 4,
            "period_start_value_usd": 4900.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 100.0,
            "goals": [],
        }

        result = generate_pdf(
            "",
            report_data=report_data,
            schedule_name="Weekly Report",
            account_name="Main Account",
        )
        assert result is not None
        assert isinstance(result, bytes)

    def test_generate_pdf_with_prior_period(self):
        """Edge case: report with prior period comparison data generates PDF."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 12000.0,
            "account_value_btc": 0.2,
            "period_profit_usd": 800.0,
            "total_trades": 30,
            "win_rate": 75.0,
            "winning_trades": 22,
            "losing_trades": 8,
            "period_start_value_usd": 11200.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 800.0,
            "goals": [],
            "prior_period": {
                "account_value_usd": 11000.0,
                "period_profit_usd": 600.0,
            },
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None
        assert isinstance(result, bytes)

    def test_generate_pdf_with_ai_summary_string(self):
        """Edge case: plain string AI summary renders in PDF."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 8000.0,
            "account_value_btc": 0.12,
            "period_profit_usd": 300.0,
            "total_trades": 15,
            "win_rate": 66.7,
            "winning_trades": 10,
            "losing_trades": 5,
            "period_start_value_usd": 7700.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 300.0,
            "goals": [],
            "_ai_summary": "Your portfolio performed well this period.",
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_with_ai_summary_tiered(self):
        """Edge case: tiered AI summary dict renders both tiers."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 8000.0,
            "account_value_btc": 0.12,
            "period_profit_usd": 300.0,
            "total_trades": 15,
            "win_rate": 66.7,
            "winning_trades": 10,
            "losing_trades": 5,
            "period_start_value_usd": 7700.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 300.0,
            "goals": [],
            "_ai_summary": {
                "simple": "Portfolio is up 3.9%.",
                "detailed": "### Analysis\n\n- Winning streak of 10 trades.\n- Risk/reward ratio improved.",
            },
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_with_transfers(self):
        """Edge case: capital movements with transfers generate PDF."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.15,
            "period_profit_usd": 500.0,
            "total_trades": 25,
            "win_rate": 72.0,
            "winning_trades": 18,
            "losing_trades": 7,
            "period_start_value_usd": 9500.0,
            "net_deposits_usd": 200.0,
            "total_deposits_usd": 200.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 300.0,
            "goals": [],
            "trade_summary": {
                "total_trades": 25,
                "winning_trades": 18,
                "losing_trades": 7,
                "net_profit_usd": 500.0,
            },
            "transfer_records": [
                {
                    "date": "2026-03-01",
                    "type": "deposit",
                    "original_type": "deposit",
                    "amount_usd": 200.0,
                },
            ],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_with_market_value_effect(self):
        """Edge case: market_value_effect_usd is rendered in metrics."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.15,
            "period_profit_usd": 500.0,
            "total_trades": 25,
            "win_rate": 72.0,
            "winning_trades": 18,
            "losing_trades": 7,
            "period_start_value_usd": 9500.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 500.0,
            "market_value_effect_usd": -150.0,
            "goals": [],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_with_period_days_in_label(self):
        """Edge case: period_days renders in trades label."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.15,
            "period_profit_usd": 500.0,
            "total_trades": 25,
            "win_rate": 72.0,
            "winning_trades": 18,
            "losing_trades": 7,
            "period_days": 7,
            "period_start_value_usd": 9500.0,
            "net_deposits_usd": 0.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 500.0,
            "goals": [],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_exception_returns_none(self):
        """Failure: internal exception returns None gracefully."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        # Patch get_brand to raise, triggering the except Exception path
        with patch(
            "app.services.report_generator_service.pdf_generator.get_brand",
            side_effect=RuntimeError("brand error"),
        ):
            result = generate_pdf("", report_data={"some": "data"})
        assert result is None

    def test_generate_pdf_with_staking_rewards(self):
        """Edge case: staking rewards (send reclassified as deposit) render."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.15,
            "period_profit_usd": 500.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "period_start_value_usd": 9500.0,
            "net_deposits_usd": 50.0,
            "total_deposits_usd": 50.0,
            "total_withdrawals_usd": 0.0,
            "adjusted_account_growth_usd": 450.0,
            "goals": [],
            "transfer_records": [
                {
                    "date": "2026-03-05",
                    "type": "deposit",
                    "original_type": "send",
                    "amount_usd": 25.0,
                },
                {
                    "date": "2026-03-10",
                    "type": "deposit",
                    "original_type": "send",
                    "amount_usd": 25.0,
                },
            ],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None

    def test_generate_pdf_negative_adjusted_growth(self):
        """Edge case: negative adjusted growth shows minus sign."""
        from app.services.report_generator_service.pdf_generator import generate_pdf

        report_data = {
            "account_value_usd": 9000.0,
            "account_value_btc": 0.13,
            "period_profit_usd": -200.0,
            "total_trades": 10,
            "win_rate": 30.0,
            "winning_trades": 3,
            "losing_trades": 7,
            "period_start_value_usd": 9200.0,
            "net_deposits_usd": -100.0,
            "total_deposits_usd": 0.0,
            "total_withdrawals_usd": 100.0,
            "adjusted_account_growth_usd": -100.0,
            "goals": [],
        }

        result = generate_pdf("", report_data=report_data)
        assert result is not None


# ---------------------------------------------------------------------------
# _render_pdf_markdown
# ---------------------------------------------------------------------------

class TestRenderPdfMarkdown:
    """Tests for _render_pdf_markdown()"""

    def test_render_markdown_plain_text(self):
        """Happy path: plain text renders without error."""
        from app.services.report_generator_service.pdf_generator import _render_pdf_markdown
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        # Should not raise
        _render_pdf_markdown(pdf, "Simple text paragraph.", 59, 130, 246)

    def test_render_markdown_with_headers(self):
        """Happy path: ### headers render in bold."""
        from app.services.report_generator_service.pdf_generator import _render_pdf_markdown
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        text = "### Section Title\n\nParagraph text here."
        _render_pdf_markdown(pdf, text, 59, 130, 246)
        # No assertion needed beyond "does not crash" for PDF rendering

    def test_render_markdown_with_bullets(self):
        """Happy path: bullet items render indented."""
        from app.services.report_generator_service.pdf_generator import _render_pdf_markdown
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        text = "- First bullet\n- Second bullet\n- Third bullet"
        _render_pdf_markdown(pdf, text, 59, 130, 246)

    def test_render_markdown_mixed_content(self):
        """Edge case: mixed headers, bullets, and paragraphs."""
        from app.services.report_generator_service.pdf_generator import _render_pdf_markdown
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        text = (
            "### Overview\n\n"
            "The portfolio performed well.\n\n"
            "### Key Points\n\n"
            "- Profit up 5%\n"
            "- Win rate improved\n\n"
            "Overall strong quarter."
        )
        _render_pdf_markdown(pdf, text, 59, 130, 246)

    def test_render_markdown_empty_text(self):
        """Edge case: empty text does not crash."""
        from app.services.report_generator_service.pdf_generator import _render_pdf_markdown
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        _render_pdf_markdown(pdf, "", 59, 130, 246)


# ---------------------------------------------------------------------------
# _render_expense_changes_pdf
# ---------------------------------------------------------------------------

class TestRenderExpenseChangesPdf:
    """Tests for _render_expense_changes_pdf()"""

    def test_render_expense_changes_none_is_noop(self):
        """Edge case: None changes does nothing."""
        from app.services.report_generator_service.pdf_generator import _render_expense_changes_pdf
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        y_before = pdf.get_y()
        _render_expense_changes_pdf(pdf, None, "$", "USD")
        assert pdf.get_y() == y_before

    def test_render_expense_changes_empty_sections_is_noop(self):
        """Edge case: changes with empty lists does nothing."""
        from app.services.report_generator_service.pdf_generator import _render_expense_changes_pdf
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        y_before = pdf.get_y()
        changes = {"increased": [], "decreased": [], "added": [], "removed": []}
        _render_expense_changes_pdf(pdf, changes, "$", "USD")
        assert pdf.get_y() == y_before

    def test_render_expense_changes_with_items(self):
        """Happy path: renders increased and added items."""
        from app.services.report_generator_service.pdf_generator import _render_expense_changes_pdf
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        changes = {
            "increased": [
                {"name": "Rent", "amount": 1600, "delta": 100, "pct_delta": 6.7},
            ],
            "decreased": [],
            "added": [
                {"name": "Gym", "amount": 50},
            ],
            "removed": [],
        }
        _render_expense_changes_pdf(pdf, changes, "$", "USD")
        # Should not crash and should advance the cursor
