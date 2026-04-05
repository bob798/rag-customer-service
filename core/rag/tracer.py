import json
import logging
from contextvars import ContextVar
from typing import Any

from core.interfaces.tracer import BaseTracer

logger = logging.getLogger(__name__)

# ContextVar ensures trace_id is per-coroutine/task, safe under async concurrency
_current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


class StructuredLogTracer(BaseTracer):
    """Emits structured JSON log lines via the logging module.

    Uses contextvars.ContextVar for trace_id so concurrent requests
    don't overwrite each other's trace context.
    """

    def start_trace(self, trace_id: str) -> None:
        _current_trace_id.set(trace_id)
        logger.info(json.dumps({"event": "trace_start", "trace_id": trace_id}))

    def log_step(self, step: str, data: dict[str, Any]) -> None:
        logger.info(
            json.dumps(
                {
                    "event": "step",
                    "trace_id": _current_trace_id.get(),
                    "step": step,
                    "data": data,
                }
            )
        )

    def end_trace(self) -> None:
        logger.info(
            json.dumps(
                {"event": "trace_end", "trace_id": _current_trace_id.get()}
            )
        )
        _current_trace_id.set("")
