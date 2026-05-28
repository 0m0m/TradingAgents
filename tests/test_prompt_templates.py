import re

import pytest

from tradingagents.agents.utils.prompts import load_prompt, render_prompt


def _placeholders(prompt: str) -> set[str]:
    return set(re.findall(r"(?<!{){([a-zA-Z_][a-zA-Z0-9_]*)}(?!})", prompt))


PROMPT_RELATIVE_PATHS = [
    "analysts/fundamentals.md",
    "analysts/market.md",
    "analysts/news.md",
    "analysts/sentiment.md",
    "managers/portfolio_manager.md",
    "managers/research_manager.md",
    "researchers/bear.md",
    "researchers/bull.md",
    "risk_mgmt/aggressive.md",
    "risk_mgmt/conservative.md",
    "risk_mgmt/neutral.md",
    "trader/system.md",
    "trader/user.md",
]


@pytest.mark.unit
class TestPromptTemplates:
    def test_loads_markdown_prompt_from_agents_prompt_dir(self):
        prompt = load_prompt("trader/system.md")

        assert "trading agent" in prompt
        assert "{language_instruction}" in prompt

    def test_renders_prompt_with_explicit_context(self):
        rendered = render_prompt(
            "trader/system.md",
            language_instruction=" Write your entire response in Chinese.",
        )

        assert "{language_instruction}" not in rendered
        assert "Write your entire response in Chinese." in rendered

    def test_missing_prompt_raises_file_not_found_error(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("does/not/exist.md")

    def test_missing_placeholder_raises_key_error(self):
        with pytest.raises(KeyError):
            render_prompt("trader/system.md")

    def test_loads_chinese_prompt(self):
        prompt = load_prompt("trader/system.md", language="Chinese")

        assert "交易" in prompt
        assert "{language_instruction}" in prompt

    def test_renders_chinese_prompt_with_explicit_context(self):
        rendered = render_prompt(
            "trader/system.md",
            language="Chinese",
            language_instruction=" 请全部使用简体中文回答。",
        )

        assert "{language_instruction}" not in rendered
        assert "请全部使用简体中文回答。" in rendered

    @pytest.mark.parametrize("relative_path", PROMPT_RELATIVE_PATHS)
    def test_chinese_prompt_placeholders_match_english(self, relative_path):
        english = load_prompt(relative_path)
        chinese = load_prompt(relative_path, language="Chinese")

        assert _placeholders(chinese) == _placeholders(english)

    def test_unknown_language_falls_back_to_english_prompt(self):
        assert load_prompt("trader/system.md", language="fr-FR") == load_prompt("trader/system.md")
