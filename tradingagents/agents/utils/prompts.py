from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_LANGUAGE_DIRS = {
    "chinese": "Chinese",
}


def _language_dir(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = language.strip().lower()
    if normalized in {"", "english"}:
        return None
    return _LANGUAGE_DIRS.get(normalized)


@lru_cache(maxsize=None)
def load_prompt(relative_path: str, language: str | None = None) -> str:
    language_dir = _language_dir(language)
    path = _PROMPTS_DIR / language_dir / relative_path if language_dir else _PROMPTS_DIR / relative_path
    if language_dir and not path.exists():
        path = _PROMPTS_DIR / relative_path
    return path.read_text(encoding="utf-8")


def render_prompt(relative_path: str, language: str | None = None, **context) -> str:
    return load_prompt(relative_path, language=language).format(**context)
