"""
Brand Service - Load and serve custom branding configuration.

Reads brand.json from branding/custom/ (falls back to branding/template/).
Caches the result at startup for fast access.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve paths relative to project root (backend/../branding/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CUSTOM_DIR = _PROJECT_ROOT / "branding" / "custom"
_TEMPLATE_DIR = _PROJECT_ROOT / "branding" / "template"

# Default brand values (fallback if no brand.json found at all)
_DEFAULTS = {
    "name": "Zenith Grid",
    "shortName": "Zenith Grid",
    "tagline": "Multi-Strategy Trading Platform",
    "loginTitle": "Zenith Grid",
    "loginTagline": "Multi-Strategy Trading Platform",
    "company": "",
    "companyLine": "",
    "copyright": "Zenith Grid",
    "defaultTheme": "classic",
    "colors": {
        "primary": "#3b82f6",
        "primaryHover": "#2563eb",
    },
    "images": {
        "loginBackground": "",
    },
}

# Cached brand config (loaded once at first access)
_brand_config: Optional[dict] = None


def _load_brand_json(path: Path) -> Optional[dict]:
    """Try to load and parse a brand.json file."""
    try:
        if path.is_file():
            with open(path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
    return None


def get_brand() -> dict:
    """Get the active brand configuration (cached after first call)."""
    global _brand_config
    if _brand_config is not None:
        return _brand_config

    # Try custom first, then template, then hardcoded defaults
    config = _load_brand_json(_CUSTOM_DIR / "brand.json")
    if config is None:
        config = _load_brand_json(_TEMPLATE_DIR / "brand.json")
    if config is None:
        logger.warning("No brand.json found, using built-in defaults")
        config = dict(_DEFAULTS)

    # Merge with defaults so missing keys don't break anything
    merged = dict(_DEFAULTS)
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    _brand_config = merged
    logger.info(
        "Brand loaded: %s (%s)",
        merged.get("shortName", "unknown"),
        "custom" if (_CUSTOM_DIR / "brand.json").is_file() else "template",
    )
    return _brand_config


def get_brand_images_dir() -> Path:
    """Get the path to the active brand's images directory."""
    custom_images = _CUSTOM_DIR / "images"
    if custom_images.is_dir() and any(custom_images.iterdir()):
        return custom_images
    return _TEMPLATE_DIR / "images"


def reload_brand() -> dict:
    """Force reload brand config (e.g., after editing brand.json)."""
    global _brand_config
    _brand_config = None
    return get_brand()
