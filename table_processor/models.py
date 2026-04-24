from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ColumnType(str, Enum):
    """Типы данных колонки, определяемые в процессе анализа."""

    INTEGER = "integer"
    FLOAT = "float"
    DATETIME = "datetime"
    DATE = "date"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    TEXT = "text"
    MIXED = "mixed"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class ChunkStrategy(str, Enum):
    """Стратегия разбиения таблицы на чанки."""

    ROW_BASED = "row_based"
    SEMANTIC = "semantic"
    AUTO = "auto"


class ColumnMeta(BaseModel):
    """Метаданные одной колонки таблицы, собираемые при инспекции листа."""

    name: str
    dtype: ColumnType
    null_ratio: float = 0.0
    unique_count: int = 0
    sample_values: list[Any] = Field(default_factory=list, max_length=5)
    top_values: dict[str, int] = Field(default_factory=dict)
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None


class SheetMeta(BaseModel):
    """Метаданные одного листа Excel-файла."""

    name: str
    row_count: int
    col_count: int
    columns: list[ColumnMeta] = Field(default_factory=list)
    header_rows: int = 1
    has_merged_cells: bool = False
    source_ref: str = ""
    warnings: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    """Один чанк таблицы — фрагмент данных, готовый к индексации или передаче в LLM."""

    id: str
    filename: str
    sheet_name: str
    strategy: ChunkStrategy
    row_start: int
    row_end: int
    row_count: int
    columns: list[str] = Field(default_factory=list)
    column_types: dict[str, ColumnType] = Field(default_factory=dict)
    source_ref: str = ""
    content: str
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Итоговый результат обработки одного файла: агрегированная статистика и список чанков."""

    filename: str
    strategy: ChunkStrategy
    sheet_count: int
    total_rows: int
    total_chunks: int
    chunks: list[Chunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
