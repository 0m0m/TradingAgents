import os
import time
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "reasoning_effort",
    "callbacks", "http_client", "http_async_client",
)


class NormalizedAzureChatOpenAI(ChatOpenAI):
    """OpenAI-compatible ChatOpenAI with normalized content output.

    Some enterprise gateways expose Azure credentials but only support the
    OpenAI-compatible `/v1/chat/completions` route. Using AzureChatOpenAI would
    force `/openai/deployments/...` paths and cause 404.
    """

    def invoke(self, input, config=None, **kwargs):
        retries = int(os.environ.get("AZURE_502_RETRIES", "10"))
        retry_delay = int(os.environ.get("AZURE_502_RETRY_DELAY", "60"))
        for attempt in range(retries + 1):
            try:
                return normalize_content(super().invoke(input, config, **kwargs))
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                message = str(exc)
                is_502 = status_code == 502 or "502" in message or "Bad Gateway" in message
                is_429 = status_code == 429
                is_invalid_payload = (
                    "model_dump" in message
                    or "'str' object has no attribute 'model_dump'" in message
                )
                if (not is_429 and not is_502 and not is_invalid_payload) or attempt >= retries:
                    raise

                # 网关 502 或网关返回 HTML/字符串伪成功：等待后重试
                time.sleep(retry_delay)


class AzureOpenAIClient(BaseLLMClient):
    """Client for Azure OpenAI deployments.

    Requires environment variables:
        AZURE_OPENAI_API_KEY: API key
        AZURE_OPENAI_ENDPOINT: Endpoint URL (e.g. https://<resource>.openai.azure.com/)
        AZURE_OPENAI_DEPLOYMENT_NAME: Deployment name
        OPENAI_API_VERSION: API version (e.g. 2025-03-01-preview)
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured OpenAI-compatible ChatOpenAI instance."""
        self.warn_if_unknown_model()

        # Keep Azure-style env var names for compatibility, but route via
        # OpenAI-compatible chat completions base URL.
        llm_kwargs = {
            "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
            "base_url": self.base_url or os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "api_key": os.environ.get("AZURE_OPENAI_API_KEY"),
            # 防止网关异常时长时间无响应导致 CLI 看起来“卡住”
            "timeout": 60,
            # 由本地 502 重试逻辑接管，避免 SDK 内部重试叠加拉长等待
            "max_retries": 0,
        }

        # Optional for compatible gateways that still expect this param name.
        # Do NOT append `api-version=v1` for pure OpenAI-compatible gateways;
        # it can break upstream routing on some proxies.
        api_version = os.environ.get("OPENAI_API_VERSION")
        if api_version and api_version.lower() != "v1":
            llm_kwargs["default_query"] = {"api-version": api_version}

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedAzureChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Azure accepts any deployed model name."""
        return True
