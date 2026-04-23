"""
Tests for the speculative calibration email body builder.

The email MUST contain a copy-pasteable prompt block that a future Claude
Code session can act on without any prior context. This test ensures
the verbatim markers + numbered steps + template holes stay intact.
"""

import pytest
from unittest.mock import patch

from app.services.email_service import (
    build_speculative_calibration_text_body,
    send_speculative_calibration_email,
)


@pytest.fixture
def analysis():
    return {
        "total_closed": 67,
        "wins": 9,
        "losses": 58,
        "overall_win_rate_pct": 13.4,
        "overall_realized_pnl_usd": -127.4,
        "components": [
            {"name": "volume_surge", "fires": 52, "win_rate_pct": 19.2},
            {"name": "compression_breakout", "fires": 41, "win_rate_pct": 17.1},
            {"name": "momentum_accelerating", "fires": 38, "win_rate_pct": 10.5},
            {"name": "micro_mid_cap", "fires": 30, "win_rate_pct": 7.0},
            {"name": "correlation_break", "fires": 33, "win_rate_pct": 4.0},
            {"name": "volume_vs_mcap", "fires": 49, "win_rate_pct": 13.0},
        ],
        "top_component": "volume_surge",
        "top_win_rate_pct": 19.2,
        "bottom_component": "correlation_break",
        "bottom_win_rate_pct": 4.0,
        "divergence_pp": 15.2,
    }


class TestBuildTextBody:
    def test_contains_copy_paste_markers(self, analysis):
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
        )
        assert "COPY EVERYTHING BELOW THIS LINE" in body
        assert "COPY EVERYTHING ABOVE THIS LINE" in body

    def test_references_speculative_signals_file_and_prp(self, analysis):
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
        )
        assert "speculative_signals.py" in body
        assert "PRPs/high-risk-doubling-preset.md" in body

    def test_renders_numbers_from_analysis(self, analysis):
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
        )
        # No template holes — every number must appear verbatim.
        assert "67" in body                     # total_closed
        assert "13.4" in body                   # overall_win_rate_pct
        assert "volume_surge" in body           # top_component
        assert "correlation_break" in body      # bottom_component
        assert "15.2" in body                   # divergence_pp
        # 9W / 58L on the same line.
        assert "9W" in body and "58L" in body

    def test_includes_user_id_in_recalibration_prompt(self, analysis):
        """The copy-paste block must be self-sufficient — the Claude session
        that receives it must be able to query for the right user_id without
        additional context."""
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
        )
        assert "user_id=42" in body

    def test_dismiss_url_is_rendered(self, analysis):
        url = (
            "https://tradebot.romerotechsolutions.com/settings"
            "?dismiss_token=XYZ&account_id=7"
        )
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url=url,
        )
        assert "dismiss_token=XYZ" in body
        assert "account_id=7" in body
        assert "/settings?" in body

    def test_proposal_block_absent_when_no_proposal(self, analysis):
        """When no proposal was generated, the email body must NOT render
        the AUTOMATED PROPOSAL section — just the Claude copy-paste block."""
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
            proposal=None, apply_url="",
        )
        assert "AUTOMATED PROPOSAL" not in body
        # Sanity: the Claude block is still there.
        assert "COPY EVERYTHING BELOW THIS LINE" in body

    def test_proposal_block_renders_before_after_table_and_apply_url(self, analysis):
        class _FakeProposal:
            algorithm = "proportional-alpha-v1"
            baseline_weights = {
                "volume_surge": 25, "compression_breakout": 20,
                "momentum_accelerating": 20, "micro_mid_cap": 10,
                "correlation_break": 10, "volume_vs_mcap": 15,
            }
            proposed_weights = {
                "volume_surge": 28, "compression_breakout": 22,
                "momentum_accelerating": 18, "micro_mid_cap": 10,
                "correlation_break": 7, "volume_vs_mcap": 15,
            }

        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
            proposal=_FakeProposal(),
            apply_url="https://x/settings?apply_token=XYZ&account_id=7&proposal_id=42",
        )
        assert "AUTOMATED PROPOSAL" in body
        assert "proportional-alpha-v1" in body
        # Current → Proposed column header.
        assert "Current" in body and "Proposed" in body
        # Delta indicators for the changed components.
        assert "(+3)" in body
        assert "(-3)" in body
        # Zero-delta component still rendered as ( 0).
        assert "( +0)" in body or "(+0)" in body or "( 0)" in body
        # Apply URL present.
        assert "apply_token=XYZ" in body
        assert "proposal_id=42" in body

    def test_proposal_block_keeps_claude_prompt_intact(self, analysis):
        """Both paths stay in the email — auto-proposal is additive."""
        class _FakeProposal:
            algorithm = "proportional-alpha-v1"
            baseline_weights = {"volume_surge": 25}
            proposed_weights = {"volume_surge": 28}

        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
            proposal=_FakeProposal(),
            apply_url="https://x/apply",
        )
        assert "AUTOMATED PROPOSAL" in body
        assert "COPY EVERYTHING BELOW THIS LINE" in body
        assert "COPY EVERYTHING ABOVE THIS LINE" in body

    def test_lists_all_components_sorted_desc(self, analysis):
        body = build_speculative_calibration_text_body(
            analysis=analysis, user_first_name="Louis", user_id=42,
            dismiss_url="https://x/dismiss?t=abc",
        )
        # Top win rate first, bottom last.
        vs_idx = body.index("volume_surge")
        cb_idx = body.index("correlation_break")
        assert vs_idx < cb_idx


class TestSendEmailCallsSES:
    def test_respects_ses_disabled_short_circuit(self, analysis):
        from app.config import settings
        prior = settings.ses_enabled
        settings.ses_enabled = False
        try:
            assert send_speculative_calibration_email(
                to="u@x.com", analysis=analysis,
                user_first_name="Louis", user_id=42,
                dismiss_url="https://x/dismiss?t=abc",
            ) is False
        finally:
            settings.ses_enabled = prior

    def test_calls_ses_with_correct_subject_and_body(self, analysis):
        from app.config import settings
        prior = settings.ses_enabled
        settings.ses_enabled = True
        try:
            with patch("app.services.email_service._send_email", return_value=True) as sender:
                result = send_speculative_calibration_email(
                    to="u@x.com", analysis=analysis,
                    user_first_name="Louis", user_id=42,
                    dismiss_url="https://x/dismiss?t=abc",
                )
                assert result is True
                sender.assert_called_once()
                args, _ = sender.call_args
                to, subject, html_body, text_body = args
                assert to == "u@x.com"
                assert "speculative" in subject.lower()
                assert "COPY EVERYTHING BELOW THIS LINE" in text_body
        finally:
            settings.ses_enabled = prior
