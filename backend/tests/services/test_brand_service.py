"""
Tests for backend/app/services/brand_service.py

Covers brand loading, caching, fallback logic, and image directory resolution.
File system access is mocked — no real brand.json files needed.
"""

import json
import pytest
from unittest.mock import patch

import app.services.brand_service as brand_mod
from app.services.brand_service import (
    _load_brand_json,
    get_brand,
    get_brand_images_dir,
    reload_brand,
    _DEFAULTS,
)


@pytest.fixture(autouse=True)
def reset_brand_cache():
    """Reset the module-level cache before each test."""
    brand_mod._brand_config = None
    yield
    brand_mod._brand_config = None


# ---------------------------------------------------------------------------
# _load_brand_json
# ---------------------------------------------------------------------------


class TestLoadBrandJson:
    """Tests for _load_brand_json()"""

    def test_valid_json_file(self, tmp_path):
        """Happy path: valid JSON file is loaded."""
        data = {"name": "TestBrand", "shortName": "TB"}
        brand_file = tmp_path / "brand.json"
        brand_file.write_text(json.dumps(data))

        result = _load_brand_json(brand_file)
        assert result == data

    def test_missing_file_returns_none(self, tmp_path):
        """Missing file returns None."""
        result = _load_brand_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        """Malformed JSON returns None (logged, not raised)."""
        brand_file = tmp_path / "brand.json"
        brand_file.write_text("{invalid json!!")

        result = _load_brand_json(brand_file)
        assert result is None

    def test_os_error_returns_none(self, tmp_path):
        """OSError during read returns None."""
        brand_file = tmp_path / "brand.json"
        brand_file.write_text("{}")

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            # is_file() still succeeds since it's pathed, but open fails
            result = _load_brand_json(brand_file)
        assert result is None

    def test_directory_path_returns_none(self, tmp_path):
        """Directory path (not a file) returns None."""
        result = _load_brand_json(tmp_path)
        assert result is None

    def test_empty_json_file_returns_empty_dict(self, tmp_path):
        """Empty JSON object file returns empty dict."""
        brand_file = tmp_path / "brand.json"
        brand_file.write_text("{}")

        result = _load_brand_json(brand_file)
        assert result == {}

    def test_json_array_file_returns_list(self, tmp_path):
        """JSON array file returns a list (valid JSON, not a dict)."""
        brand_file = tmp_path / "brand.json"
        brand_file.write_text("[]")

        result = _load_brand_json(brand_file)
        assert result == []


# ---------------------------------------------------------------------------
# get_brand
# ---------------------------------------------------------------------------


class TestGetBrand:
    """Tests for get_brand()"""

    def test_uses_custom_brand_json(self, tmp_path):
        """Happy path: custom brand.json is loaded and merged with defaults."""
        custom_config = {"name": "CustomBot", "shortName": "CB"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            # Create custom brand.json
            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(custom_config))

            result = get_brand()

        assert result["name"] == "CustomBot"
        assert result["shortName"] == "CB"
        # Defaults for missing keys should still be present
        assert result["tagline"] == _DEFAULTS["tagline"]
        assert result["colors"] == _DEFAULTS["colors"]

    def test_falls_back_to_template(self, tmp_path):
        """When custom brand.json is missing, template is used."""
        template_config = {"name": "TemplateBrand"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            # No custom dir — only template
            template_dir = tmp_path / "template"
            template_dir.mkdir()
            (template_dir / "brand.json").write_text(json.dumps(template_config))

            result = get_brand()

        assert result["name"] == "TemplateBrand"

    def test_falls_back_to_defaults_when_no_files(self, tmp_path):
        """When no brand.json files exist, hardcoded defaults are used."""
        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            result = get_brand()

        assert result["name"] == _DEFAULTS["name"]
        assert result["shortName"] == _DEFAULTS["shortName"]
        assert result["colors"] == _DEFAULTS["colors"]

    def test_deep_merge_nested_dicts(self, tmp_path):
        """Nested dicts (like colors) are merged, not replaced entirely."""
        custom_config = {
            "colors": {"primary": "#ff0000"},
        }

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(custom_config))

            result = get_brand()

        # Custom primary overrides default
        assert result["colors"]["primary"] == "#ff0000"
        # Default primaryHover is preserved
        assert result["colors"]["primaryHover"] == _DEFAULTS["colors"]["primaryHover"]

    def test_caching_returns_same_object(self, tmp_path):
        """Second call returns cached result without reloading."""
        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            result1 = get_brand()
            result2 = get_brand()

        assert result1 is result2

    def test_extra_keys_in_brand_json_preserved(self, tmp_path):
        """Extra keys in brand.json not in defaults are preserved."""
        custom_config = {"customField": "custom_value"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(custom_config))

            result = get_brand()

        assert result["customField"] == "custom_value"

    def test_scalar_override_replaces_default_dict(self, tmp_path):
        """Scalar value in brand.json replaces a default dict key."""
        custom_config = {"colors": "red"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(custom_config))

            result = get_brand()

        # Scalar replaces the dict since isinstance check fails
        assert result["colors"] == "red"

    def test_custom_preferred_over_template(self, tmp_path):
        """Custom brand.json takes priority even when template also exists."""
        custom_config = {"name": "CustomBrand"}
        template_config = {"name": "TemplateBrand"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(custom_config))

            template_dir = tmp_path / "template"
            template_dir.mkdir()
            (template_dir / "brand.json").write_text(
                json.dumps(template_config)
            )

            result = get_brand()

        assert result["name"] == "CustomBrand"

    def test_empty_brand_json_uses_all_defaults(self, tmp_path):
        """Empty brand.json ({}) results in all default values."""
        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text("{}")

            result = get_brand()

        assert result["name"] == _DEFAULTS["name"]
        assert result["tagline"] == _DEFAULTS["tagline"]
        assert result["colors"] == _DEFAULTS["colors"]
        assert result["images"] == _DEFAULTS["images"]


# ---------------------------------------------------------------------------
# get_brand_images_dir
# ---------------------------------------------------------------------------


class TestGetBrandImagesDir:
    """Tests for get_brand_images_dir()"""

    def test_custom_images_dir_when_populated(self, tmp_path):
        """Returns custom images dir when it exists and has files."""
        custom_images = tmp_path / "custom" / "images"
        custom_images.mkdir(parents=True)
        (custom_images / "logo.png").write_text("fake")

        template_images = tmp_path / "template" / "images"
        template_images.mkdir(parents=True)

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            result = get_brand_images_dir()

        assert result == custom_images

    def test_falls_back_to_template_when_custom_empty(self, tmp_path):
        """Returns template images dir when custom dir is empty."""
        custom_images = tmp_path / "custom" / "images"
        custom_images.mkdir(parents=True)
        # Empty — no files

        template_images = tmp_path / "template" / "images"
        template_images.mkdir(parents=True)

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            result = get_brand_images_dir()

        assert result == template_images

    def test_falls_back_to_template_when_custom_missing(self, tmp_path):
        """Returns template images dir when custom images dir doesn't exist."""
        template_images = tmp_path / "template" / "images"
        template_images.mkdir(parents=True)

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            result = get_brand_images_dir()

        assert result == template_images


# ---------------------------------------------------------------------------
# reload_brand
# ---------------------------------------------------------------------------


class TestReloadBrand:
    """Tests for reload_brand()"""

    def test_reload_clears_cache_and_reloads(self, tmp_path):
        """reload_brand() clears cache and returns fresh config."""
        config_v1 = {"name": "Version1"}
        config_v2 = {"name": "Version2"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            brand_file = custom_dir / "brand.json"
            brand_file.write_text(json.dumps(config_v1))

            result1 = get_brand()
            assert result1["name"] == "Version1"

            # Update the file and reload
            brand_file.write_text(json.dumps(config_v2))
            result2 = reload_brand()

        assert result2["name"] == "Version2"
        assert result1 is not result2

    def test_reload_returns_merged_defaults(self, tmp_path):
        """reload_brand() returns config merged with defaults."""
        config = {"name": "ReloadTest"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            (custom_dir / "brand.json").write_text(json.dumps(config))

            result = reload_brand()

        assert result["name"] == "ReloadTest"
        # Defaults are still merged in
        assert result["tagline"] == _DEFAULTS["tagline"]
        assert result["colors"] == _DEFAULTS["colors"]

    def test_reload_falls_back_to_defaults_when_file_deleted(self, tmp_path):
        """reload_brand() falls back to defaults when brand.json is deleted."""
        config = {"name": "WillBeDeleted"}

        with patch.object(brand_mod, "_CUSTOM_DIR", tmp_path / "custom"), \
             patch.object(brand_mod, "_TEMPLATE_DIR", tmp_path / "template"):

            custom_dir = tmp_path / "custom"
            custom_dir.mkdir()
            brand_file = custom_dir / "brand.json"
            brand_file.write_text(json.dumps(config))

            result1 = get_brand()
            assert result1["name"] == "WillBeDeleted"

            # Delete the file and reload
            brand_file.unlink()
            result2 = reload_brand()

        assert result2["name"] == _DEFAULTS["name"]
