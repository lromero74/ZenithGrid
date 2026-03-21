"""
Tests for disposable email detection service.
"""
import pytest
from app.services.disposable_email_service import (
    is_disposable_domain,
    looks_machine_generated,
    is_suspicious_email,
    is_disposable_email,
    get_disposable_domains,
)


class TestIsDisposableDomain:
    def test_known_disposable_domain_flagged(self):
        assert is_disposable_domain("user@mailinator.com") is True

    def test_guerrillamail_flagged(self):
        assert is_disposable_domain("test@guerrillamail.com") is True

    def test_yopmail_flagged(self):
        assert is_disposable_domain("test@yopmail.com") is True

    def test_lnovic_flagged(self):
        # The one that got us
        assert is_disposable_domain("1qe9k827b1@lnovic.com") is True

    def test_gmail_not_flagged(self):
        assert is_disposable_domain("anyone@gmail.com") is False

    def test_outlook_not_flagged(self):
        assert is_disposable_domain("user@outlook.com") is False

    def test_yahoo_not_flagged(self):
        assert is_disposable_domain("user@yahoo.com") is False

    def test_protonmail_not_flagged(self):
        assert is_disposable_domain("user@protonmail.com") is False

    def test_custom_domain_not_flagged(self):
        assert is_disposable_domain("user@mycompany.io") is False

    def test_missing_at_symbol(self):
        assert is_disposable_domain("notanemail") is False

    def test_case_insensitive_domain(self):
        # Domain is lowercased before lookup — uppercase should still be flagged
        assert is_disposable_domain("user@MAILINATOR.COM") is True

    def test_uppercase_local_part_no_effect(self):
        # Only the domain matters, not the local part case
        assert is_disposable_domain("User@mailinator.com") is True


class TestLooksMachineGenerated:
    def test_obvious_random_string_flagged(self):
        # 1qe9k827b1: digits=5 (1,9,8,2,7,1), vowels=1 (e)
        # Wait: 1,q,e,9,k,8,2,7,b,1 -> digits: 1,9,8,2,7,1 = 6, vowels: e = 1
        assert looks_machine_generated("1qe9k827b1") is True

    def test_another_random_string(self):
        # Only letters and many digits, very few vowels
        assert looks_machine_generated("x7k2m9p3n8r1") is True

    def test_james194_not_flagged(self):
        # Only 3 digits — below threshold of 5
        assert looks_machine_generated("james194") is False

    def test_jsmith42_not_flagged(self):
        # Only 2 digits
        assert looks_machine_generated("jsmith42") is False

    def test_john_not_flagged(self):
        assert looks_machine_generated("john") is False

    def test_username_with_year_not_flagged(self):
        # 4 digits but real-looking
        assert looks_machine_generated("sarah2024") is False

    def test_too_short_not_flagged(self):
        assert looks_machine_generated("abc123") is False  # < 8 chars

    def test_has_separator_not_flagged(self):
        # Dots/hyphens/underscores are excluded — looks like a real address
        assert looks_machine_generated("a.b9k2m8") is False

    def test_many_vowels_not_flagged(self):
        # Real word patterns have vowels
        assert looks_machine_generated("emailuser123") is False  # 'e','a','i','u' = 4 vowels

    def test_too_long_not_flagged(self):
        assert looks_machine_generated("a" * 21) is False  # > 20 chars


class TestIsSuspiciousEmail:
    def test_disposable_domain_suspicious(self):
        suspicious, reason = is_suspicious_email("test@mailinator.com")
        assert suspicious is True
        assert reason == "disposable_domain"

    def test_lnovic_suspicious(self):
        suspicious, reason = is_suspicious_email("1qe9k827b1@lnovic.com")
        assert suspicious is True
        assert reason == "disposable_domain"  # domain check fires first

    def test_random_local_on_gmail_suspicious(self):
        suspicious, reason = is_suspicious_email("x7k2m9p3n8r1@gmail.com")
        assert suspicious is True
        assert reason == "machine_generated"

    def test_normal_gmail_not_suspicious(self):
        suspicious, reason = is_suspicious_email("james194@gmail.com")
        assert suspicious is False
        assert reason == ""

    def test_real_address_not_suspicious(self):
        suspicious, reason = is_suspicious_email("louis_romero@outlook.com")
        assert suspicious is False
        assert reason == ""

    def test_missing_at_not_suspicious(self):
        suspicious, reason = is_suspicious_email("notanemail")
        assert suspicious is False
        assert reason == ""


class TestGetDisposableDomains:
    def test_returns_list(self):
        domains = get_disposable_domains()
        assert isinstance(domains, list)
        assert len(domains) > 10

    def test_includes_known_domains(self):
        domains = get_disposable_domains()
        assert "mailinator.com" in domains
        assert "lnovic.com" in domains

    def test_sorted(self):
        domains = get_disposable_domains()
        assert domains == sorted(domains)


class TestIsDisposableEmail:
    """Backward-compat wrapper — delegates to is_suspicious_email."""

    def test_disposable_returns_true(self):
        assert is_disposable_email("test@mailinator.com") is True

    def test_machine_generated_returns_true(self):
        assert is_disposable_email("x7k2m9p3n8r1@gmail.com") is True

    def test_normal_returns_false(self):
        assert is_disposable_email("james194@gmail.com") is False
