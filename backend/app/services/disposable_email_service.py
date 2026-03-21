"""
Disposable Email Domain Detection

Checks whether an email address uses a well-known throwaway/disposable email
service. Only flags domains that are unambiguously throwaway providers — no
false positives on legitimate addresses like james194@gmail.com.
"""

# Known disposable/throwaway email domains.
# Keep this list conservative: only unambiguous throwaway-only services.
DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    # Mailinator family
    "mailinator.com", "mailinator.net", "mailinator.org",
    "mailinater.com", "suremail.info", "spamfloz.com",
    # Guerrilla Mail family
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "guerrillamail.de", "guerrillamail.biz", "guerrillamail.info",
    "guerrillamailblock.com", "grr.la", "spam4.me",
    # Trash Mail / Temp Mail services
    "trashmail.com", "trashmail.at", "trashmail.io", "trashmail.me",
    "trashmail.net", "trashmail.org", "trash-mail.at",
    "trashmailer.com",
    "tempmail.com", "tempmail.net", "tempmail.org",
    "temp-mail.org", "temp-mail.io",
    "throwam.com",
    # YopMail family
    "yopmail.com", "yopmail.fr",
    "cool.fr.nf", "jetable.fr.nf", "nospam.ze.tc", "nomail.xl.cx",
    "mega.zik.dj", "speed.1s.fr",
    # SpamGourmet / SpamFree
    "spamgourmet.com", "spamgourmet.net", "spamgourmet.org",
    "spamfree24.org", "spamfree.eu",
    # Other well-known throwaway providers
    "sharklasers.com",
    "spamavert.com",
    "mailnull.com",
    "netmails.net",
    "dispostable.com",
    "maildrop.cc",
    "getairmail.com",
    "fakeinbox.com",
    "discard.email",
    "boximail.com",
    "crapmail.org",
    "tempr.email",
    "0-mail.com",
    "spamhereplease.com",
    "tmailor.com",
    "getnada.com",
    "mailnesia.com",
    "mailforspam.com",
    "throwam.com",
    # The one that got us
    "lnovic.com",
})


def is_disposable_domain(email: str) -> bool:
    """Return True if the email's domain is a known throwaway provider."""
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower().strip()
    return domain in DISPOSABLE_DOMAINS


def looks_machine_generated(local_part: str) -> bool:
    """
    Return True if the email local part looks machine-generated.

    Conservative heuristic — designed to catch things like `1qe9k827b1`
    without flagging legitimate short-hand names like `james194` or `jsmith42`.

    Signals:
    - All lowercase alphanumeric (no separators like dots/hyphens/underscores)
    - Length 8–20 (too short = nickname, too long = probably a real domain email)
    - At least 5 digits (high digit density signals random generation)
    - At most 1 vowel (real names/words contain vowels; random strings usually don't)
    """
    lp = local_part.lower()
    if not lp.isalnum():
        return False  # Contains dots, hyphens, underscores — looks like a real address
    if not (8 <= len(lp) <= 20):
        return False
    digit_count = sum(1 for c in lp if c.isdigit())
    if digit_count < 5:
        return False  # james194 has only 3 digits — safe
    vowel_count = sum(1 for c in lp if c in "aeiou")
    if vowel_count > 1:
        return False  # Real words/names have vowels
    return True


def is_suspicious_email(email: str) -> tuple[bool, str]:
    """
    Check whether an email looks like a throwaway or bot registration.

    Returns (is_suspicious, reason) where reason is one of:
      'disposable_domain' — domain is a known throwaway provider
      'machine_generated' — local part looks auto-generated
      ''                  — not suspicious
    """
    if "@" not in email:
        return False, ""
    local, domain = email.lower().rsplit("@", 1)
    if domain.strip() in DISPOSABLE_DOMAINS:
        return True, "disposable_domain"
    if looks_machine_generated(local.strip()):
        return True, "machine_generated"
    return False, ""


# Keep old name for backward compatibility in signup endpoint
def is_disposable_email(email: str) -> bool:
    suspicious, _ = is_suspicious_email(email)
    return suspicious


def get_disposable_domains() -> list[str]:
    """Return the sorted list of known disposable domains (for frontend sync)."""
    return sorted(DISPOSABLE_DOMAINS)
