import tempfile
import textwrap
import unittest
from pathlib import Path


class TestAppConfig(unittest.TestCase):
    def test_default_loader_reads_repo_config(self):
        from modcord.config.app_configuration import app_config

        data = app_config.data
        self.assertIsInstance(data, dict)
        self.assertIn("system_prompt", data)
        self.assertTrue(app_config.system_prompt_template)

    def test_missing_config_path_returns_empty_data(self):
        from modcord.config.app_configuration import AppConfig

        cfg = AppConfig(config_path=Path("does_not_exist_12345.yml"))
        self.assertEqual(cfg.data, {})
        self.assertEqual(cfg.system_prompt_template, "")
        self.assertEqual(cfg.server_rules, "")

    def test_format_system_prompt_and_shortcuts(self):
        from modcord.config.app_configuration import AppConfig

        yaml_content = textwrap.dedent(
            """
            system_prompt: "Moderate using:{SERVER_RULES}"
            server_rules: "Be nice"
            ai_settings:
              enabled: true
              allow_gpu: false
            """
        )

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yml") as tmp:
            tmp.write(yaml_content)
            tmp_path = Path(tmp.name)

        try:
            cfg = AppConfig(config_path=tmp_path)
            self.assertEqual(cfg.server_rules, "Be nice")
            self.assertTrue(cfg.ai_settings["enabled"])

            formatted = cfg.format_system_prompt("Follow the rules")
            self.assertIn("Follow the rules", formatted)
            self.assertNotIn("{SERVER_RULES}", formatted)

            fallback = cfg.format_system_prompt("", template_override="Rules: {SERVER_RULES}")
            self.assertEqual(fallback, "Rules: ")
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
