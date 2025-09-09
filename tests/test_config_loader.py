import unittest
from pathlib import Path

class TestConfigLoader(unittest.TestCase):
    def test_load_config_default_path(self):
        from src.modcord.config_loader import load_config
        cfg = load_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn('server_rules', cfg)
        self.assertIn('system_prompt', cfg)
        self.assertTrue(len(cfg['system_prompt']) > 0)

    def test_load_config_invalid_path(self):
        from src.modcord.config_loader import load_config
        cfg = load_config(path=str(Path('does_not_exist_12345.yml')))
        self.assertEqual(cfg, {})

    def test_get_server_rules_precedence(self):
        from src.modcord.config_loader import load_config, get_server_rules
        cfg = load_config()
        default_rules = get_server_rules(cfg)
        self.assertIsInstance(default_rules, str)
        # guild rules should take precedence when provided
        overridden = get_server_rules(cfg, guild_rules="Guild overrides config")
        self.assertEqual(overridden, "Guild overrides config")

    def test_get_system_prompt_formatting(self):
        from src.modcord.config_loader import load_config, get_system_prompt
        cfg = load_config()
        # When server_rules provided, placeholder should be replaced
        rules = "Rule A; Rule B"
        prompt = get_system_prompt(cfg, server_rules=rules)
        self.assertIn(rules, prompt)
        # When None provided, should not raise and should return template
        template_only = get_system_prompt(cfg)
        self.assertIn("{SERVER_RULES}", template_only)

if __name__ == '__main__':
    unittest.main()
