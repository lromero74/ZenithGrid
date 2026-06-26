from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "deployment" / "nginx-zenithgrid-lightsail.conf"


def test_lightsail_nginx_serves_frontend_directly():
    config = CONFIG.read_text()

    assert "root /var/www/zenithgrid/current;" in config
    assert "location ^~ /api/" in config
    assert "location ^~ /ws" in config
    assert "try_files $uri $uri/ /index.html;" in config
    assert 'Cache-Control "no-cache"' in config
    assert 'Cache-Control "public, max-age=31536000, immutable"' in config
