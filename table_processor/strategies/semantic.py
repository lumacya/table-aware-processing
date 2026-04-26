from __future__ import annotations

from pathlib import Path

from pandas import DataFrame

from table_processor.models import Chunk, ChunkStrategy, SheetMeta
from table_processor.strategies.base import BaseChunkStrategy
from table_processor.strategies.row_based import (
    RowBasedStrategy,
    _build_summary,
    _df_to_text,
)
from table_processor.utils import make_source_ref as _make_source_ref
from table_processor.utils import pick_group_column as _pick_group_column

# Максимальное количество строк в одной семантической группе
MAX_GROUP_ROWS = 200


def _build_semantic_summary(
    df: DataFrame,
    sheet_meta: SheetMeta,
    group_col: str,
    group_val: str,
) -> str:
    """Строит summary для семантического чанка:
    добавляет заголовок группировки к стандартному summary."""
    row_start = int(df.index[0]) if len(df) > 0 else 0
    row_end = int(df.index[-1]) if len(df) > 0 else 0
    base = _build_summary(df, sheet_meta, row_start, row_end)
    return f"Группировка: {group_col} = {group_val}\n{base}"


class SemanticStrategy(BaseChunkStrategy):
    """Стратегия нарезки таблицы по смысловым группам
    на основе значений ключевой колонки."""

    def __init__(
        self,
        group_column: str | None = None,
        chunk_size: int = 50,
        max_cells_per_chunk: int = 10_000,
        max_bytes_per_chunk: int | None = None,
    ) -> None:
        self._group_column = group_column
        self._chunk_size = chunk_size
        self._max_cells_per_chunk = max_cells_per_chunk
        self._max_bytes_per_chunk = max_bytes_per_chunk

    @property
    def strategy_type(self) -> ChunkStrategy:
        return ChunkStrategy.SEMANTIC

    def split(
        self, df: DataFrame, sheet_meta: SheetMeta, source_file: Path
    ) -> list[Chunk]:
        """Нарезает DataFrame по группам ключевой колонки;
        при отсутствии откатывается к row-based."""
        group_col = self._group_column or _pick_group_column(sheet_meta)

        # Откат к row-based если группировочная колонка не определена или отсутствует
        if group_col is None or group_col not in df.columns:
            return RowBasedStrategy(
                chunk_size=self._chunk_size,
                max_cells_per_chunk=self._max_cells_per_chunk,
                max_bytes_per_chunk=self._max_bytes_per_chunk,
            ).split(df, sheet_meta, source_file)

        file_stem = source_file.stem
        sheet_safe = sheet_meta.name.replace(" ", "_")
        col_count = len(df.columns)
        chunks: list[Chunk] = []

        for group_val, group_df in df.groupby(group_col, sort=False):
            group_val_str = str(group_val)
            indices = list(group_df.index)

            # Большие группы дробим через RowBasedStrategy
            if len(group_df) > MAX_GROUP_ROWS:
                sub_chunks = RowBasedStrategy(
                    chunk_size=self._chunk_size,
                    max_cells_per_chunk=self._max_cells_per_chunk,
                    max_bytes_per_chunk=self._max_bytes_per_chunk,
                ).split(group_df.reset_index(drop=True), sheet_meta, source_file)
                for chunk in sub_chunks:
                    chunk.metadata["group_column"] = group_col
                    chunk.metadata["group_value"] = group_val_str
                chunks.extend(sub_chunks)
                continue

            col_safe = group_col.replace(" ", "_")
            val_safe = group_val_str.replace(" ", "_")[:30]
            chunk_id = f"{file_stem}__{sheet_safe}__{col_safe}_{val_safe}"

            is_contiguous = (indices[-1] - indices[0] + 1) == len(indices)
            source_ref = _make_source_ref(
                sheet_meta.name,
                len(group_df),
                col_count,
                row_offset=indices[0] + sheet_meta.header_rows,
            )

            metadata: dict = {
                "group_column": group_col,
                "group_value": group_val_str,
            }
            if not is_contiguous:
                metadata["row_indices"] = indices

            chunks.append(
                Chunk(
                    id=chunk_id,
                    filename=source_file.name,
                    sheet_name=sheet_meta.name,
                    strategy=ChunkStrategy.SEMANTIC,
                    row_start=indices[0],
                    row_end=indices[-1],
                    row_count=len(group_df),
                    columns=[str(c) for c in df.columns],
                    column_types={
                        c.name: c.dtype
                        for c in sheet_meta.columns
                        if c.name in {str(col) for col in df.columns}
                    },
                    source_ref=source_ref,
                    content=_df_to_text(group_df),
                    summary=_build_semantic_summary(
                        group_df, sheet_meta, group_col, group_val_str
                    ),
                    metadata=metadata,
                )
            )

        return chunks
