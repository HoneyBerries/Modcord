import json
from pathlib import Path

import pytest

from modcord.configuration.app_configuration import AISettings, AppConfig


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "app_config.yml"


def test_app_config_reload_parses_yaml(config_path: Path) -> None:
    config_payload = {
        "server_rules": "Be kind.",
        "system_prompt": "Rules: {SERVER_RULES}",
        "ai_settings": {
            "enabled": True,
            "vram_percentage": 0.75,
            "model_id": "test-model",
                "moderation_batch_seconds": 5,
                "sampling_parameters": {"max_new_tokens": 256, "temperature": 0.2},
        },
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    config = AppConfig(config_path)

    assert config.get("default_server_rules") == "Be kind."
    assert config.server_rules == "Be kind."
    assert config.system_prompt_template == "Rules: {SERVER_RULES}"

    ai_settings = config.ai_settings
    assert ai_settings.enabled is True
    assert ai_settings.vram_percentage == pytest.approx(0.75)
    assert ai_settings.model_id == "test-model"
    assert ai_settings.get("moderation_batch_seconds") == 5
    assert ai_settings.sampling_parameters == {"max_new_tokens": 256, "temperature": 0.2}


def test_app_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.yml"

    config = AppConfig(missing_path)

    assert config.data == {}
    assert config.server_rules == ""
    assert config.system_prompt_template == ""

    ai_settings = config.ai_settings
    assert ai_settings.enabled is False
    assert ai_settings.model_id is None
    assert ai_settings.knobs == {}


def test_app_config_format_system_prompt_fallback(config_path: Path) -> None:
    config_payload = {
        "system_prompt": "Hello {UNKNOWN}",
        "ai_settings": {},
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    config = AppConfig(config_path)

    prompt = config.system_prompt_template
    assert "Hello {UNKNOWN}" in prompt


def test_ai_settings_mapping_and_defaults() -> None:
    settings = AISettings(
        {
            "enabled": "yes",
            "vram_percentage": "0.5",
            "model_id": 42,
                "sampling_parameters": ["not", "a", "dict"],
            "extra_field": "value",
        }
    )

    assert settings.enabled is True
    assert settings.vram_percentage == pytest.approx(0.5)
    assert settings.model_id == "42"
    assert settings.sampling_parameters == {}
    assert settings.get("extra_field") == "value"
    assert set(iter(settings)) == set(settings.as_dict().keys())
    assert list(iter(settings))
    assert len(settings) == len(settings.as_dict())
    assert settings["enabled"] == "yes"
