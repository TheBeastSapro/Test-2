"""OpenAI and Anthropic adapters.

Written against the HTTP APIs directly rather than the vendor SDKs: two fewer
dependencies, and the request shape stays visible where you can reason about cost.

Model IDs move fast. They are constructor defaults, not hard-coded, so you can
override per channel without redeploying.
"""

from __future__ import annotations

import json
import re

import httpx

from ..credits import USD_PER_CREDIT
from .base import LLMProvider, ProviderError, ProviderTimeout, TextResult

# USD per million tokens (input, output). Update alongside vendor price changes;
# these drive the credit charge, so being wrong here means losing money quietly.
TOKEN_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
_DEFAULT_PRICE = (3.00, 15.00)
_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


def _credits_for_tokens(model: str, prompt_tokens: int, completion_tokens: int) -> int:
    in_price, out_price = TOKEN_PRICES.get(model, _DEFAULT_PRICE)
    usd = (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
    # Charge at 2x provider cost; text is cheap enough that the floor of 1 dominates.
    return max(1, round(usd * 2 / USD_PER_CREDIT))


def extract_json(text: str) -> dict:
    """Models wrap JSON in prose or fences more often than they should."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError(f"model did not return valid JSON: {exc}") from exc
    raise ProviderError("model did not return valid JSON")


class OpenAIProvider(LLMProvider):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    def __init__(self, api_key: str = "", model: str = "gpt-4o") -> None:
        super().__init__(api_key)
        self.model = model

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_object: bool = False,
        schema_name: str = "",
    ) -> TextResult:
        key = self._require_key()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_object:
            body["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

        _raise_for_status(response, self.name)
        payload = response.json()
        usage = payload.get("usage", {})
        return TextResult(
            text=payload["choices"][0]["message"]["content"] or "",
            credits=_credits_for_tokens(
                self.model,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            ),
            provider=self.name,
            model=self.model,
            meta={"usage": usage, "schema_name": schema_name},
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    base_url = "https://api.anthropic.com/v1"
    api_version = "2023-06-01"

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-5") -> None:
        super().__init__(api_key)
        self.model = model

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_object: bool = False,
        schema_name: str = "",
    ) -> TextResult:
        key = self._require_key()
        if json_object:
            # Anthropic has no JSON response mode; prefilling '{' is the reliable
            # way to force a bare object with no preamble.
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"},
            ]
        else:
            messages = [{"role": "user", "content": prompt}]

        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            body["system"] = system

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": self.api_version,
                        "content-type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

        _raise_for_status(response, self.name)
        payload = response.json()
        text = "".join(
            block.get("text", "") for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        if json_object:
            text = "{" + text  # put back the prefilled brace
        usage = payload.get("usage", {})
        return TextResult(
            text=text,
            credits=_credits_for_tokens(
                self.model,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            ),
            provider=self.name,
            model=self.model,
            meta={"usage": usage, "schema_name": schema_name},
        )


def _raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.is_success:
        return
    # 429 and 5xx are worth another attempt; 4xx means the request is wrong.
    retryable = response.status_code == 429 or response.status_code >= 500
    detail = response.text[:500]
    raise ProviderError(
        f"{provider} returned {response.status_code}: {detail}",
        provider=provider,
        retryable=retryable,
    )
