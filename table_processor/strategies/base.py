from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pandas import DataFrame

from table_processor.models import Chunk, ChunkStrategy, SheetMeta


class BaseChunkStrategy(ABC):
    """Абстрактный базовый класс для стратегий чанкинга.
    Определяет контракт, обязательный к реализации."""

    @property
    @abstractmethod
    def strategy_type(self) -> ChunkStrategy:
        """Возвращает тип стратегии чанкинга."""

    @abstractmethod
    def split(
        self, df: DataFrame, sheet_meta: SheetMeta, source_file: Path
    ) -> list[Chunk]:
        """Нарезает DataFrame на чанки и возвращает их список."""
