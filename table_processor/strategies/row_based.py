from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas import DataFrame

from table_processor.models import Chunk, ChunkStrategy, ColumnType, SheetMeta
from table_processor.strategies.base import BaseChunkStrategy
from table_processor.utils import make_source_ref as _make_source_ref

# Числовые типы колонок для которых строится статистика диапазона
_NUMERIC_TYPES = {ColumnType.INTEGER, ColumnType.FLOAT}


def _df_to_text(df: DataFrame) -> str:
    """Конвертирует DataFrame в читаемый текст с разделителями."""
    cols = [str(c) for c in df.columns]
    header = " | ".join(cols)
    separator = "-" * len(header)
    text_df = df.fillna("").astype(str)
    data_rows = text_df.apply(lambda row: " | ".join(row), axis=1).tolist()
    rows: list[str] = [header, separator] + data_rows
    return "\n".join(rows)


def _build_summary(
    df: DataFrame,
    sheet_meta: SheetMeta,
    row_start: int,
    row_end: int,
) -> str:
    """Строит краткое текстовое описание чанка для retrieval."""
    col_names = [str(c) for c in df.columns]
    preview = _df_to_text(df.head(3))

    lines = [
        f"Sheet: {sheet_meta.name}",
        f"Columns: {', '.join(col_names)}",
        f"Rows {row_start}-{row_end}:",
        preview,
    ]

    # Числовая статистика для числовых колонок
    col_type_map = {c.name: c.dtype for c in sheet_meta.columns}
    for col_name in col_names:
        if col_type_map.get(col_name) not in _NUMERIC_TYPES:
            continue
        if col_name not in df.columns:
            continue
        numeric = pd.to_numeric(
            df[col_name].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        ).dropna()
        if numeric.empty:
            continue
        lines.append(
            f"{col_name}: min={numeric.min():.2f}, max={numeric.max():.2f},"
            f" mean={numeric.mean():.2f}, sum={numeric.sum():.2f}"
        )

    return "\n".join(lines)


def _estimate_row_bytes(row: pd.Series) -> int:
    """Считает примерный размер строки в байтах
    через UTF-8 кодирование непустых значений."""
    return int(row.dropna().astype(str).str.encode("utf-8").str.len().sum())


class RowBasedStrategy(BaseChunkStrategy):
    """Стратегия нарезки таблицы на блоки фиксированного размера по N строк."""

    def __init__(
        self,
        chunk_size: int = 50,
        max_cells_per_chunk: int = 10_000,
        max_bytes_per_chunk: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.max_cells_per_chunk = max_cells_per_chunk
        self.max_bytes_per_chunk = max_bytes_per_chunk

    @property
    def strategy_type(self) -> ChunkStrategy:
        return ChunkStrategy.ROW_BASED

    def _make_chunk(
        self,
        block: DataFrame,
        start: int,
        col_count: int,
        sheet_meta: SheetMeta,
        source_file: Path,
        col_type_map: dict,
        chunk_index: int,
        effective_chunk_size: int,
        extra_meta: dict | None = None,
    ) -> Chunk:
        """Собирает объект Chunk из блока строк."""
        row_count = len(block)
        end = start + row_count - 1
        chunk_id = (
            f"{source_file.stem}__{sheet_meta.name.replace(' ', '_')}"
            f"__rows_{start}_{end}"
        )
        source_ref = _make_source_ref(
            sheet_meta.name,
            row_count,
            col_count,
            row_offset=start + sheet_meta.header_rows,
        )
        metadata: dict = {
            "chunk_index": chunk_index,
            "chunk_size": effective_chunk_size,
        }
        if extra_meta:
            metadata.update(extra_meta)
        block_col_names = {str(c) for c in block.columns}
        return Chunk(
            id=chunk_id,
            filename=source_file.name,
            sheet_name=sheet_meta.name,
            strategy=ChunkStrategy.ROW_BASED,
            row_start=start,
            row_end=end,
            row_count=row_count,
            columns=[str(c) for c in block.columns],
            column_types={
                name: dtype
                for name, dtype in col_type_map.items()
                if name in block_col_names
            },
            source_ref=source_ref,
            content=_df_to_text(block),
            summary=_build_summary(block, sheet_meta, start, end),
            metadata=metadata,
        )

    def _flush_oversized(
        self,
        df: DataFrame,
        block_rows: list[int],
        block_start: int,
        col_count: int,
        sheet_meta: SheetMeta,
        source_file: Path,
        col_type_map: dict,
        chunk_index: int,
    ) -> Chunk:
        """Создаёт чанк из одиночной строки превысившей лимит байт."""
        block = df.iloc[block_rows]
        return self._make_chunk(
            block, block_start, col_count, sheet_meta, source_file,
            col_type_map, chunk_index, 1, {"oversized_row": True},
        )

    def split(
        self, df: DataFrame, sheet_meta: SheetMeta, source_file: Path
    ) -> list[Chunk]:
        """Нарезает DataFrame на чанки по строкам или по байтам
        если задан max_bytes_per_chunk."""
        col_count = len(df.columns)
        col_type_map = {c.name: c.dtype for c in sheet_meta.columns}
        chunks: list[Chunk] = []
        chunk_index = 0

        if self.max_bytes_per_chunk is not None:
            # Нарезка по байтам: накапливаем строки до превышения лимита
            row_bytes_list = (
                df.fillna("").astype(str)
                .apply(lambda row: sum(len(v.encode("utf-8")) for v in row), axis=1)
                .tolist()
            )
            block_rows: list[int] = []
            current_bytes = 0
            block_start = 0

            for i in range(len(df)):
                row_bytes = row_bytes_list[i]

                if not block_rows:
                    # Первая строка нового блока — всегда включаем
                    block_rows.append(i)
                    current_bytes = row_bytes
                    block_start = i
                    # Одиночная строка превышает лимит — сохраняем как oversized
                    if row_bytes > self.max_bytes_per_chunk:
                        chunks.append(self._flush_oversized(
                            df, block_rows, block_start, col_count,
                            sheet_meta, source_file, col_type_map, chunk_index,
                        ))
                        chunk_index += 1
                        block_rows = []
                        current_bytes = 0
                elif current_bytes + row_bytes <= self.max_bytes_per_chunk:
                    block_rows.append(i)
                    current_bytes += row_bytes
                else:
                    # Лимит достигнут — сохраняем накопленный блок
                    block = df.iloc[block_rows]
                    chunks.append(self._make_chunk(
                        block, block_start, col_count, sheet_meta, source_file,
                        col_type_map, chunk_index, len(block_rows),
                    ))
                    chunk_index += 1
                    # Начинаем новый блок с текущей строки
                    block_rows = [i]
                    current_bytes = row_bytes
                    block_start = i
                    if row_bytes > self.max_bytes_per_chunk:
                        chunks.append(self._flush_oversized(
                            df, block_rows, block_start, col_count,
                            sheet_meta, source_file, col_type_map, chunk_index,
                        ))
                        chunk_index += 1
                        block_rows = []
                        current_bytes = 0

            # Остаток
            if block_rows:
                block = df.iloc[block_rows]
                chunks.append(self._make_chunk(
                    block, block_start, col_count, sheet_meta, source_file,
                    col_type_map, chunk_index, len(block_rows),
                ))
        else:
            # Нарезка по строкам
            effective_chunk_size = min(
                self.chunk_size,
                self.max_cells_per_chunk // max(col_count, 1),
            )
            for start in range(0, len(df), effective_chunk_size):
                end = min(start + effective_chunk_size, len(df))
                block = df.iloc[start:end]
                chunks.append(self._make_chunk(
                    block, start, col_count, sheet_meta, source_file,
                    col_type_map, chunk_index, effective_chunk_size,
                ))
                chunk_index += 1

        return chunks
