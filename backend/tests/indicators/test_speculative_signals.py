"""
Tests for backend/app/indicators/speculative_signals.py

Each weight component gets a dedicated "fires only this" test so a
future calibration session can compare per-component win rates against
the corresponding test's expected input shape.
"""

from app.indicators.speculative_signals import (
    WEIGHTS,
    components_for_log,
    score_speculative_setup,
    summarize_components_for_prompt,
)


class TestWeightsInvariant:
    def test_weights_sum_to_100(self):
        """Foundational invariant: the score must be a 0-100 percentage."""
        assert sum(WEIGHTS.values()) == 100

    def test_weights_have_expected_components(self):
        """Regression guard on the public component list."""
        expected = {
            "volume_surge",
            "compression_breakout",
            "momentum_accelerating",
            "micro_mid_cap",
            "correlation_break",
            "volume_vs_mcap",
        }
        assert set(WEIGHTS.keys()) == expected


class TestScoreBoundaries:
    def test_empty_metrics_returns_zero(self):
        """Failure case: no data → score 0, all components not fired."""
        result = score_speculative_setup({})
        assert result["score"] == 0
        for name in WEIGHTS:
            assert result["components"][name]["fired"] is False
            assert result["components"][name]["contribution"] == 0

    def test_all_components_fire_sums_to_100(self):
        """Happy path: everything fires → exactly 100 (sum of weights)."""
        metrics = {
            "volume_30d_ratio": 5.0,
            "compression_ratio": 5.0,
            "momentum_1h": 3.0,
            "momentum_acceleration": 1.0,
            "listing_age_days": 30,
            "is_major_cap": False,
            "turnover_ratio_24h": 0.1,
        }
        btc = {"momentum_1h": -1.0}  # 4.0 delta → correlation_break fires
        result = score_speculative_setup(metrics, btc, "HYPE-USD")
        assert result["score"] == 100

    def test_non_dict_metrics_treated_as_empty(self):
        """Defensive: garbage input must not crash the scorer."""
        result = score_speculative_setup(None)
        assert result["score"] == 0


class TestVolumeSurge:
    def test_fires_at_threshold(self):
        result = score_speculative_setup({"volume_30d_ratio": 3.0})
        assert result["components"]["volume_surge"]["fired"] is True
        assert result["components"]["volume_surge"]["contribution"] == WEIGHTS["volume_surge"]

    def test_does_not_fire_below_threshold(self):
        result = score_speculative_setup({"volume_30d_ratio": 2.99})
        assert result["components"]["volume_surge"]["fired"] is False
        assert result["components"]["volume_surge"]["contribution"] == 0

    def test_missing_ratio_does_not_fire(self):
        result = score_speculative_setup({})
        assert result["components"]["volume_surge"]["fired"] is False


class TestCompressionBreakout:
    def test_fires_with_positive_momentum(self):
        result = score_speculative_setup({
            "compression_ratio": 4.0,
            "momentum_1h": 0.5,
        })
        assert result["components"]["compression_breakout"]["fired"] is True

    def test_does_not_fire_without_positive_momentum(self):
        """Compression on its own isn't enough — needs momentum confirmation."""
        result = score_speculative_setup({
            "compression_ratio": 4.0,
            "momentum_1h": -0.5,
        })
        assert result["components"]["compression_breakout"]["fired"] is False

    def test_does_not_fire_below_ratio(self):
        result = score_speculative_setup({
            "compression_ratio": 2.9,
            "momentum_1h": 2.0,
        })
        assert result["components"]["compression_breakout"]["fired"] is False


class TestMomentumAccelerating:
    def test_fires_when_positive_and_fast(self):
        result = score_speculative_setup({
            "momentum_acceleration": 0.1,
            "momentum_1h": 2.5,
        })
        assert result["components"]["momentum_accelerating"]["fired"] is True

    def test_does_not_fire_with_weak_momentum(self):
        result = score_speculative_setup({
            "momentum_acceleration": 1.0,
            "momentum_1h": 1.5,  # below 2.0% floor
        })
        assert result["components"]["momentum_accelerating"]["fired"] is False

    def test_does_not_fire_decelerating(self):
        result = score_speculative_setup({
            "momentum_acceleration": -0.5,
            "momentum_1h": 3.0,
        })
        assert result["components"]["momentum_accelerating"]["fired"] is False


class TestMicroMidCap:
    def test_fires_on_recent_listing(self):
        result = score_speculative_setup({"listing_age_days": 45})
        assert result["components"]["micro_mid_cap"]["fired"] is True

    def test_fires_when_flagged_non_major(self):
        """Fallback heuristic: caller says this is not a major cap."""
        result = score_speculative_setup({"is_major_cap": False})
        assert result["components"]["micro_mid_cap"]["fired"] is True

    def test_does_not_fire_on_old_major(self):
        result = score_speculative_setup({
            "listing_age_days": 5000,
            "is_major_cap": True,
        })
        assert result["components"]["micro_mid_cap"]["fired"] is False

    def test_does_not_fire_with_no_hints(self):
        """No listing age, no major-cap flag → cannot determine → not fired."""
        result = score_speculative_setup({})
        assert result["components"]["micro_mid_cap"]["fired"] is False


class TestCorrelationBreak:
    def test_fires_when_coin_diverges_from_btc(self):
        result = score_speculative_setup(
            {"momentum_1h": 4.0},
            {"momentum_1h": 0.0},
        )
        assert result["components"]["correlation_break"]["fired"] is True

    def test_does_not_fire_when_coin_tracks_btc(self):
        result = score_speculative_setup(
            {"momentum_1h": 1.0},
            {"momentum_1h": 1.5},
        )
        assert result["components"]["correlation_break"]["fired"] is False

    def test_does_not_fire_without_btc_metrics(self):
        """Failure case: missing BTC reference → component inactive."""
        result = score_speculative_setup({"momentum_1h": 4.0})
        assert result["components"]["correlation_break"]["fired"] is False


class TestVolumeVsMcap:
    def test_fires_on_high_turnover(self):
        result = score_speculative_setup({"turnover_ratio_24h": 0.08})
        assert result["components"]["volume_vs_mcap"]["fired"] is True

    def test_does_not_fire_on_low_turnover(self):
        result = score_speculative_setup({"turnover_ratio_24h": 0.01})
        assert result["components"]["volume_vs_mcap"]["fired"] is False


class TestRenderingHelpers:
    def test_summarize_when_nothing_fires(self):
        result = score_speculative_setup({})
        text = summarize_components_for_prompt(result)
        assert "0/100" in text
        assert "no components fired" in text.lower()

    def test_summarize_lists_fired_components(self):
        metrics = {"volume_30d_ratio": 5.0, "turnover_ratio_24h": 0.08}
        result = score_speculative_setup(metrics)
        text = summarize_components_for_prompt(result)
        assert "volume_surge" in text
        assert "volume_vs_mcap" in text

    def test_components_for_log_is_deterministic(self):
        metrics = {"volume_30d_ratio": 5.0}
        a = components_for_log(score_speculative_setup(metrics))
        b = components_for_log(score_speculative_setup(metrics))
        assert a == b
        # Includes all components, in the canonical order
        names = [row[0] for row in a]
        assert names == list(WEIGHTS.keys())
