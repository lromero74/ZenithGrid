"""
Tests for the PostgreSQL data-corruption detector.

is_db_corruption_error() must recognise physical storage / bad-block errors
(so background loops can degrade gracefully) while NOT matching ordinary query
errors or non-database exceptions (so genuine bugs still propagate / fail fast).
"""

import pytest
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError

from app.utils.db_corruption import is_db_corruption_error


def _wrap(orig_message: str, cls=OperationalError):
    """Build a SQLAlchemy DBAPIError whose wrapped (orig) message is orig_message."""
    return cls("SELECT 1", {}, Exception(orig_message))


class TestIsDbCorruptionError:
    @pytest.mark.parametrize(
        "message",
        [
            'could not read block 5 in file "base/16384/1": Input/output error',
            "invalid page in block 12 of relation base/16384/2619",
            "missing chunk number 0 for toast value 54321 in pg_toast_2619",
            "could not open file \"base/16384/1\": Input/output error",
        ],
    )
    def test_corruption_signatures_detected(self, message):
        """Known physical-corruption signatures are recognised (happy path)."""
        assert is_db_corruption_error(_wrap(message)) is True

    def test_detection_is_case_insensitive(self):
        """Matching ignores case so capitalised driver messages still match (edge case)."""
        assert is_db_corruption_error(_wrap("COULD NOT READ BLOCK 9")) is True

    def test_ordinary_query_error_not_flagged(self):
        """A normal SQL error must NOT be treated as corruption (failure case)."""
        assert is_db_corruption_error(_wrap("syntax error at or near", ProgrammingError)) is False

    def test_data_error_without_signature_not_flagged(self):
        """A DataError without a corruption signature is a real bug, not corruption."""
        assert is_db_corruption_error(_wrap("value too long for type", DataError)) is False

    def test_non_database_exception_not_flagged(self):
        """Non-DBAPI exceptions are never corruption, even with a matching string."""
        assert is_db_corruption_error(ValueError("could not read block")) is False
