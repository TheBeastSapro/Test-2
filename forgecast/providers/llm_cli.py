"""LLM access through the local `claude` CLI — no API key required.

This is the honest version of "use the sandbox login". There is no login that grants
an application free programmatic model access: platforms that appear to offer it are
holding their own API key and reselling it through credits. What *is* available is the
`claude` CLI, which authenticates with an existing Claude subscription on this machine.
Shelling out to it gives real scripts and real research at no incremental cost.

**Where this works and where it does not.** Perfect for private, single-operator use —
your subscription, your machine, no key to manage. It does *not* scale to a hosted
multi-user site: the CLI is tied to one interactive login, so every user would need
their own, and running it server-side on your login to serve customers would be both
technically fragile and a licensing problem. When you have paying users, hold a real
API key and meter it through the credit ledger, which is the model the ledger was
built for.

Cost is reported as 0 credits because the subscription is already paid. That keeps the
ledger honest rather than inventing a price for something that did not bill.
"""

from __future__ import annotations

import asyncio
import logging
import shutil

from .base import LLMProvider, ProviderError, ProviderTimeout, TextResult

log = logging.getLogger("forgecast.providers.llm_cli")

CLAUDE_BIN = shutil.which("claude")
DEFAULT_TIMEOUT = 300.0

JSON_NUDGE = (
    "Respond with a single valid JSON object and nothing else. No prose, no markdown "
    "fences, no explanation before or after."
)


class ClaudeCliProvider(LLMProvider):
    """Runs `claude -p` as a subprocess and returns its stdout."""

    name = "claude-cli"

    def __init__(self, api_key: str = "", binary: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        super().__init__(api_key)
        self.binary = binary or CLAUDE_BIN
        self.timeout = timeout
        self.model = "claude-cli"

    def available(self) -> bool:
        return bool(self.binary)

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
        if not self.binary:
            raise ProviderError(
                "the `claude` CLI is not installed. Install Claude Code, or configure "
                "an API-key provider instead.",
                provider=self.name,
            )

        # The CLI takes one prompt, so the system prompt is prepended rather than
        # passed separately. `--append-system-prompt` exists but behaves differently
        # across versions; inlining is stable.
        parts = []
        if system:
            parts.append(system)
        if json_object:
            parts.append(JSON_NUDGE)
        parts.append(prompt)
        composed = "\n\n".join(parts)

        argv = [self.binary, "-p", composed]
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"`claude -p` did not finish within {self.timeout:.0f}s",
                provider=self.name,
            ) from exc
        except OSError as exc:
            raise ProviderError(f"could not run {self.binary}: {exc}",
                                provider=self.name) from exc

        text = (stdout or b"").decode(errors="replace").strip()
        if process.returncode != 0 or not text:
            detail = (stderr or b"").decode(errors="replace")[-400:].strip()
            raise ProviderError(
                f"`claude -p` failed (exit {process.returncode}): "
                f"{detail or 'no output'}",
                provider=self.name,
                # A non-zero exit here is usually auth or rate limiting, both of
                # which can clear on their own.
                retryable=True,
            )

        return TextResult(
            text=text,
            credits=0,     # covered by the subscription; do not invent a charge
            provider=self.name,
            model=self.model,
            meta={
                "schema_name": schema_name,
                "via": "claude-cli",
                "billing": "subscription — no per-call charge",
            },
        )
