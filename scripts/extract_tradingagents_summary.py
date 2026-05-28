from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_TRADINGAGENTS_ROOT = Path("D:/tools/TradingAgents")
DEFAULT_SUMMARY_PROVIDER = "openai"
DEFAULT_OPENAI_BACKEND_URL = "https://a.0m0m.link/nai/v1"
MINIMAX_CN_PROVIDER = "minimax-cn"


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(module_name: str):
    module_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary_fields() -> list[str]:
    row_builder = _load_module("build_tradingagents_summary_row")
    return list(row_builder.SUMMARY_FIELDS)


def _build_prompt(report_path: Path) -> str:
    fields = ", ".join(_summary_fields())
    report_text = report_path.read_text(encoding="utf-8")
    return (
        f"请根据这个 TradingAgents markdown 报告文件提炼摘要，文件路径：{report_path}。"
        "报告全文如下：\n"
        f"{report_text}\n"
        "只返回一个 JSON 对象，不要 markdown 代码块，不要附加解释。"
        f"顶层 key 必须且只能使用这些字段：{fields}，并额外包含 status 和 error。"
        "无法判断的字段使用空字符串。"
        "key_catalysts 和 key_risks 必须使用简体中文字符串数组。"
        "除 status 和 error 外，所有字符串字段必须使用简体中文。"
        'status 使用 "completed"，error 使用空字符串。'
    )


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    return str(content)


def _is_minimax_model(model: str) -> bool:
    return model.lower().startswith("minimax")


def _resolve_summary_provider(provider: str, model: str) -> str:
    if _is_minimax_model(model):
        return MINIMAX_CN_PROVIDER
    return provider


def _resolve_summary_base_url(provider: str, base_url: str | None) -> str | None:
    if base_url:
        return base_url
    if provider.lower() == "openai":
        return (
            os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
            or DEFAULT_OPENAI_BACKEND_URL
        )
    return None


def _load_dotenv_if_present(tradingagents_root: Path) -> None:
    dotenv_path = tradingagents_root / ".env"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path)


def _create_summary_llm(
    model: str,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    tradingagents_root: Path = DEFAULT_TRADINGAGENTS_ROOT,
    base_url: str | None = None,
) -> Any:
    root = str(tradingagents_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    _load_dotenv_if_present(tradingagents_root)

    from tradingagents.llm_clients.factory import create_llm_client

    client = create_llm_client(
        provider=provider,
        model=model,
        base_url=base_url,
    )
    return client.get_llm()


def _run_tradingagents_python(
    code: str,
    tradingagents_root: Path = DEFAULT_TRADINGAGENTS_ROOT,
    extra_env: dict[str, str] | None = None,
) -> str:
    import subprocess

    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["uv", "run", "python", "-c", code],
        cwd=tradingagents_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or "TradingAgents summary LLM failed"
        )
    return completed.stdout


def _run_summary_llm_subprocess(
    prompt: str,
    model: str,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    tradingagents_root: Path = DEFAULT_TRADINGAGENTS_ROOT,
    base_url: str | None = None,
) -> str:
    payload_json = json.dumps(
        {
            "prompt": prompt,
            "model": model,
            "provider": provider,
            "base_url": base_url,
        },
        ensure_ascii=False,
    )
    code = """
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from tradingagents.llm_clients.factory import create_llm_client

payload = json.loads(os.environ['TRADINGAGENTS_SUMMARY_PAYLOAD'])
load_dotenv(Path('.env'))
load_dotenv(Path('.env.enterprise'), override=False)
client = create_llm_client(
    provider=payload['provider'],
    model=payload['model'],
    base_url=payload['base_url'],
)
llm = client.get_llm()
response = llm.invoke(payload['prompt'])
content = getattr(response, 'content', response)
print(content if isinstance(content, str) else str(content))
"""
    return _run_tradingagents_python(
        code,
        tradingagents_root=tradingagents_root,
        extra_env={"TRADINGAGENTS_SUMMARY_PAYLOAD": payload_json},
    )


def _run_summary_llm(
    prompt: str,
    model: str,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    tradingagents_root: Path = DEFAULT_TRADINGAGENTS_ROOT,
    base_url: str | None = None,
) -> str:
    if tradingagents_root == DEFAULT_TRADINGAGENTS_ROOT:
        return _run_summary_llm_subprocess(
            prompt,
            model=model,
            provider=provider,
            tradingagents_root=tradingagents_root,
            base_url=base_url,
        )
    llm = _create_summary_llm(
        model=model,
        provider=provider,
        tradingagents_root=tradingagents_root,
        base_url=base_url,
    )
    return _response_text(llm.invoke(prompt))


def _extract_json_payload(stdout: str) -> dict[str, object]:
    text = stdout.strip()
    if not text:
        raise ValueError("empty summary response")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("summary response is not valid JSON") from None
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("summary response must be a JSON object")
    return payload


def _build_repair_prompt(original_prompt: str, stdout: str) -> str:
    return (
        f"{original_prompt}"
        "上一次回答没有包含可解析 JSON。"
        "请只根据原报告文件重新输出一个合法 JSON 对象，不要 markdown 代码块，不要附加解释。"
        f"上一次回答如下：{stdout[-2000:]}"
    )


def _normalize_summary(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {field: "" for field in _summary_fields()}
    for field in _summary_fields():
        if field in payload:
            normalized[field] = payload[field]
    normalized["status"] = payload.get("status") or "completed"
    normalized["error"] = payload.get("error") or ""
    return normalized


def build_error_summary(error: str) -> dict[str, object]:
    payload = {field: "" for field in _summary_fields()}
    payload["status"] = "pending_summary"
    payload["error"] = error
    return payload


def extract_tradingagents_summary(
    report_path: Path,
    model: str | None = None,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    tradingagents_root: Path = DEFAULT_TRADINGAGENTS_ROOT,
    base_url: str | None = None,
) -> dict[str, object]:
    prompt = _build_prompt(report_path)
    summary_model = model or "MiniMax-M2.7"
    summary_provider = _resolve_summary_provider(provider, summary_model)
    summary_base_url = _resolve_summary_base_url(summary_provider, base_url)
    stdout = _run_summary_llm(
        prompt,
        model=summary_model,
        provider=summary_provider,
        tradingagents_root=tradingagents_root,
        base_url=summary_base_url,
    )
    try:
        payload = _extract_json_payload(stdout)
    except ValueError:
        repair_prompt = _build_repair_prompt(prompt, stdout)
        stdout = _run_summary_llm(
            repair_prompt,
            model=summary_model,
            provider=summary_provider,
            tradingagents_root=tradingagents_root,
            base_url=summary_base_url,
        )
        payload = _extract_json_payload(stdout)
    return _normalize_summary(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--model")
    parser.add_argument("--provider", default=DEFAULT_SUMMARY_PROVIDER)
    parser.add_argument("--tradingagents-root", default=str(DEFAULT_TRADINGAGENTS_ROOT))
    parser.add_argument("--base-url")
    args = parser.parse_args(argv)

    try:
        payload = extract_tradingagents_summary(
            report_path=Path(args.report_path),
            model=args.model,
            provider=args.provider,
            tradingagents_root=Path(args.tradingagents_root),
            base_url=args.base_url,
        )
        exit_code = 0
    except Exception as exc:
        payload = build_error_summary(str(exc))
        exit_code = 1

    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
