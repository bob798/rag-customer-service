from typing import Optional

import litellm


class LLMFactory:
    """Adapter for LiteLLM with optional fallback model support."""

    def __init__(self, model: str, fallback: Optional[str] = None) -> None:
        self.model = model
        self.fallback = fallback

    async def complete(
        self, messages: list[dict], stream: bool = False, **kwargs
    ) -> str:
        """Call LiteLLM acompletion.

        When stream=False (default): returns string content from the response.
        When stream=True: returns the raw response object for caller iteration.

        Falls back to self.fallback model on any Exception, if fallback is set.
        Re-raises the original exception if no fallback is configured.
        """
        try:
            response = await litellm.acompletion(
                model=self.model, messages=messages, stream=stream, **kwargs
            )
        except Exception:
            if self.fallback is None:
                raise
            response = await litellm.acompletion(
                model=self.fallback, messages=messages, stream=stream, **kwargs
            )

        if stream:
            return response

        return response.choices[0].message.content

    async def complete_stream(self, messages: list[dict], **kwargs):
        """Call LiteLLM with stream=True and return the raw stream for async iteration."""
        return await litellm.acompletion(
            model=self.model, messages=messages, stream=True, **kwargs
        )
