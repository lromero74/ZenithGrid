"""Guards for the reversible web/trader systemd deployment."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment"


def test_split_units_assign_distinct_roles_and_ports():
    web = (DEPLOYMENT / "zenithgrid-web.service").read_text()
    trader = (DEPLOYMENT / "zenithgrid-trader.service").read_text()

    assert "Environment=PROCESS_ROLE=web" in web
    assert "--port 8100" in web
    assert "Environment=PROCESS_ROLE=trader" in trader
    assert "--port 8101" in trader


def test_cutover_is_self_verifying_and_rolls_back_to_combined():
    script = (DEPLOYMENT / "enable-split-processes.sh").read_text()

    assert "rollback_to_combined" in script
    assert '"--rollback"' in script
    assert 'process_role\\\":\\\"${role}' in script
    assert "disable --now zenithgrid.service" in script


def test_ship_script_restarts_both_services_after_cutover():
    script = (DEPLOYMENT / "ship-lightsail.sh").read_text()

    assert "zenithgrid-web.service" in script
    assert "zenithgrid-trader.service" in script
    assert "process_role" in script
