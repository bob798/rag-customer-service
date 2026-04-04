import logging
from typing import Any, Optional, Union

import litellm

logger = logging.getLogger(__name__)


class LLMFactory:
    """Adapter for LiteLLM with optional fallback model support."""

    def __init__(self, model: str, fallback: Optional[str] = None) -> None:
        self.model = model
        self.fallback = fallback

    async def complete(
        self, messages: list[dict[str, str]], stream: bool = False, **kwargs
    ) -> Union[str, Any]:
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
        except Exception as exc:
            if self.fallback is None:
                raise
            logger.warning(
                "Primary model %r failed (%s); retrying with fallback %r",
                self.model,
                exc,
                self.fallback,
            )
            response = await litellm.acompletion(
                model=self.fallback, messages=messages, stream=stream, **kwargs
            )

        if stream:
            return response

        return response.choices[0].message.content

    async def complete_stream(
        self, messages: list[dict[str, str]], **kwargs
    ) -> Any:
        """Call LiteLLM with stream=True and return the raw stream for async iteration.

        Falls back to self.fallback model on any Exception, if fallback is set.
        Re-raises the original exception if no fallback is configured.
        """
        try:
            return await litellm.acompletion(
                model=self.model, messages=messages, stream=True, **kwargs
            )
        except Exception as exc:
            if self.fallback is None:
                raise
            logger.warning(
                "Primary model %r failed (%s); retrying with fallback %r",
                self.model,
                exc,
                self.fallback,
            )
            return await litellm.acompletion(
                model=self.fallback, messages=messages, stream=True, **kwargs
            )
