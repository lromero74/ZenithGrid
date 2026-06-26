from types import SimpleNamespace

from app import database


class DummyPool:
    def __init__(self):
        self._size = 10
        self._checked_in = 3
        self._checked_out = 7
        self._overflow = 2

    def size(self):
        return self._size

    def checkedin(self):
        return self._checked_in

    def checkedout(self):
        return self._checked_out

    def overflow(self):
        return self._overflow


def test_pool_capacity_snapshot_reports_write_and_read_pool_pressure(monkeypatch):
    pool = DummyPool()
    dummy_engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))
    monkeypatch.setattr(database, "engine", dummy_engine)
    monkeypatch.setattr(database, "read_engine", dummy_engine)

    snapshot = database.get_pool_capacity_snapshot()

    assert snapshot["write"]["checked_out"] == 7
    assert snapshot["write"]["capacity"] == 12
    assert snapshot["write"]["utilization_pct"] == 58.33
    assert snapshot["read"]["checked_in"] == 3
