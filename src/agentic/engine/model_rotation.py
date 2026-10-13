# src/agentic/engine/model_rotation.py
"""Reusable model rotation for free-tier quotas."""
import itertools
import threading
from typing import Sequence

from src.schemas.llm_models import LLMModels


class ModelRotation:
    """Thread-safe model rotator over a fixed sequence of models."""

    def __init__(self, models: Sequence[LLMModels]):
        self.models = tuple(models)
        self._lock = threading.Lock()
        self._cycle = itertools.cycle(self.models)

    def next(self) -> LLMModels:
        with self._lock:
            return next(self._cycle)

    def reset(self) -> None:
        with self._lock:
            self._cycle = itertools.cycle(self.models)

    def __iter__(self):
        return self

    def __next__(self) -> LLMModels:
        return self.next()


TASK_MODELS = (LLMModels.GEMINI_3_5_FLASH_LITE, LLMModels.GEMINI_3_1_FLASH_LITE)
LIBRARIAN_MODELS = (LLMModels.GEMMA_31B, LLMModels.GEMMA_26B)

task_rotation = ModelRotation(TASK_MODELS)
librarian_rotation = ModelRotation(LIBRARIAN_MODELS)

__all__ = [
    "ModelRotation",
    "TASK_MODELS",
    "LIBRARIAN_MODELS",
    "task_rotation",
    "librarian_rotation",
]
