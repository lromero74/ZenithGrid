from app.performance_metrics import (
    clear_performance_samples,
    get_performance_snapshot,
    record_client_timings,
    record_server_timing,
)


def setup_function():
    clear_performance_samples()


def test_server_snapshot_reports_bounded_route_percentiles_without_identity_data():
    for duration in (1, 2, 3, 4, 100):
        record_server_timing("GET", "/api/positions/", duration)

    snapshot = get_performance_snapshot()

    assert snapshot["server"]["GET /api/positions/"] == {
        "count": 5,
        "p50_ms": 3.0,
        "p95_ms": 100.0,
        "max_ms": 100.0,
    }
    assert "user" not in str(snapshot).lower()
    assert "account" not in str(snapshot).lower()


def test_client_snapshot_accepts_only_bounded_startup_measures():
    record_client_timings("/positions", {
        "zenith:bootstrap-to-positions-data-ready": 123.4,
        "email": 5,
        "zenith:bootstrap-to-invalid": 999_999,
    })

    client = get_performance_snapshot()["client"]
    assert list(client) == ["/positions zenith:bootstrap-to-positions-data-ready"]
    assert client[next(iter(client))]["p50_ms"] == 123.4
