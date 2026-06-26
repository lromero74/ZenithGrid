import importlib


def _load_server_resources(monkeypatch, role: str):
    monkeypatch.setenv("PROCESS_ROLE", role)
    module = importlib.import_module("app.server_resources")
    module = importlib.reload(module)
    monkeypatch.setattr(module, "_get_pg_max_connections", lambda: 100)
    return module


def test_split_process_pool_budgets_fit_postgres(monkeypatch):
    server_resources = _load_server_resources(monkeypatch, "web")
    web_plan = server_resources.ResourcePlan()

    server_resources = _load_server_resources(monkeypatch, "trader")
    trader_plan = server_resources.ResourcePlan()

    split_total = (
        web_plan.write_pool_size
        + web_plan.write_pool_overflow
        + web_plan.read_pool_size
        + web_plan.read_pool_overflow
        + trader_plan.write_pool_size
        + trader_plan.write_pool_overflow
        + trader_plan.read_pool_size
        + trader_plan.read_pool_overflow
    )

    assert web_plan.process_role == "web"
    assert trader_plan.process_role == "trader"
    assert web_plan.monitor_slots == 0
    assert trader_plan.api_slots == 0
    assert split_total <= web_plan.usable


def test_web_role_keeps_small_responsive_pool(monkeypatch):
    server_resources = _load_server_resources(monkeypatch, "web")
    plan = server_resources.ResourcePlan()

    assert plan.write_pool_size + plan.write_pool_overflow <= 18
    assert plan.read_pool_size + plan.read_pool_overflow <= 8
    assert plan.bot_concurrency_max == 0
    assert plan.pair_concurrency_max == 0


def test_trader_role_keeps_headroom_for_web_and_postgres(monkeypatch):
    server_resources = _load_server_resources(monkeypatch, "trader")
    plan = server_resources.ResourcePlan()

    assert plan.write_pool_size + plan.write_pool_overflow <= 19
    assert plan.bot_concurrency_max <= 2
    assert plan.pair_concurrency_max <= 2
