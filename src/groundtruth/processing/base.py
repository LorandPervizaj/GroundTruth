"""Abstract base classes for processing components."""

from abc import ABC, abstractmethod
from typing import TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class Processor[InputT, OutputT](ABC):
    """Base interface for all processors. Each must be independently unit-testable."""

    @abstractmethod
    def process(self, value: InputT, **context) -> OutputT:
        """Transform input to output."""
        ...
