from __future__ import annotations

from pathlib import Path

from table_processor.analyzer import analyze_file
from table_processor.loader import load_file
from table_processor.models import ChunkStrategy, ProcessingResult, SheetMeta
from table_processor.strategies.base import BaseChunkStrategy
from table_processor.strategies.row_based import RowBasedStrategy
from table_processor.strategies.semantic import SemanticStrategy
from table_processor.utils import pick_group_column


def _select_strategy(
    sheet_metas: dict[str, SheetMeta],
    requested: ChunkStrategy,
    chunk_size: int,
    max_cells_per_chunk: int,
    max_bytes_per_chunk: int | None = None,
) -> BaseChunkStrategy:
    """Выбирает стратегию чанкинга; AUTO определяет её автоматически
    по наличию группировочных колонок."""
    if requested == ChunkStrategy.ROW_BASED:
        return RowBasedStrategy(
            chunk_size=chunk_size,
            max_cells_per_chunk=max_cells_per_chunk,
            max_bytes_per_chunk=max_bytes_per_chunk,
        )

    if requested == ChunkStrategy.SEMANTIC:
        return SemanticStrategy(
            chunk_size=chunk_size,
            max_cells_per_chunk=max_cells_per_chunk,
            max_bytes_per_chunk=max_bytes_per_chunk,
        )

    # AUTO: семантика если хотя бы один лист имеет подходящую колонку для группировки
    has_group_col = any(
        pick_group_column(meta) is not None for meta in sheet_metas.values()
    )
    if has_group_col:
        return SemanticStrategy(
            chunk_size=chunk_size,
            max_cells_per_chunk=max_cells_per_chunk,
            max_bytes_per_chunk=max_bytes_per_chunk,
        )
    return RowBasedStrategy(
        chunk_size=chunk_size,
        max_cells_per_chunk=max_cells_per_chunk,
        max_bytes_per_chunk=max_bytes_per_chunk,
    )


def process_file(
    file_path: str | Path,
    strategy: ChunkStrategy = ChunkStrategy.AUTO,
    chunk_size: int = 50,
    max_cells_per_chunk: int = 10_000,
    display_name: str | None = None,
    max_bytes_per_chunk: int | None = None,
) -> ProcessingResult:
    """Главная публичная функция: загружает файл, анализирует и нарезает на чанки."""
    path = Path(file_path)
    display_path = Path(display_name) if display_name else path

    # Загрузка и анализ
    sheets = load_file(path, display_name=display_name)
    sheet_metas = analyze_file(sheets, path)

    # Выбор стратегии
    chunk_strategy = _select_strategy(
        sheet_metas, strategy, chunk_size, max_cells_per_chunk, max_bytes_per_chunk
    )

    # Нарезка всех листов
    all_chunks = []
    for sheet_name, df in sheets.items():
        meta = sheet_metas[sheet_name]
        all_chunks.extend(chunk_strategy.split(df, meta, display_path))

    # Сбор предупреждений со всех листов
    warnings: list[str] = []
    for meta in sheet_metas.values():
        warnings.extend(meta.warnings)

    # Предупреждение если фактическая стратегия отличается от запрошенной
    actual_strategy = (
        all_chunks[0].strategy if all_chunks else chunk_strategy.strategy_type
    )
    if actual_strategy == ChunkStrategy.ROW_BASED:
        for chunk in all_chunks:
            chunk.metadata.pop("group_column", None)
            chunk.metadata.pop("group_value", None)
    if (
        strategy != ChunkStrategy.AUTO
        and actual_strategy != chunk_strategy.strategy_type
    ):
        warnings.append(
            f"Стратегия {strategy.value} недоступна,"
            f" использована {actual_strategy.value}"
        )

    return ProcessingResult(
        filename=display_path.name,
        strategy=actual_strategy,
        sheet_count=len(sheets),
        total_rows=sum(meta.row_count for meta in sheet_metas.values()),
        total_chunks=len(all_chunks),
        chunks=all_chunks,
        warnings=warnings,
        sheets=sheet_metas,
    )
