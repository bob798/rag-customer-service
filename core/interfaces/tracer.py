from abc import ABC, abstractmethod
from typing import Any


class BaseTracer(ABC):
    @abstractmethod
    def start_trace(self, trace_id: str) -> None:
        """Start a new trace."""
        ...

    @abstractmethod
    def log_step(self, step: str, data: dict[str, Any]) -> None:
        """Log a step with associated data."""
        ...

    @abstractmethod
    def end_trace(self) -> None:
        """End the current trace."""
        ...
