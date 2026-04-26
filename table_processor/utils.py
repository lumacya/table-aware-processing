"""Вспомогательные утилиты для работы с Excel-нотацией."""
from __future__ import annotations

from table_processor.models import ColumnType, SheetMeta

# Приоритет типов колонок для выбора группировочной колонки
_GROUP_PRIORITY = [
    ColumnType.CATEGORICAL,
    ColumnType.DATE,
    ColumnType.DATETIME,
    ColumnType.BOOLEAN,
]


def col_letter(n: int) -> str:
    """Конвертирует номер колонки (1-based) в Excel-букву: 1→A, 27→AA."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def make_source_ref(
    sheet_name: str,
    row_count: int,
    col_count: int,
    row_offset: int = 0,
) -> str:
    """Строит ссылку на диапазон в Excel-нотации: SheetName!A{start}:{col}{end}."""
    start_row = row_offset + 1
    end_row = row_offset + row_count
    end_col = col_letter(col_count)
    return f"{sheet_name}!A{start_row}:{end_col}{end_row}"


def pick_group_column(sheet_meta: SheetMeta) -> str | None:
    """Выбирает лучшую колонку для группировки
    по приоритету типа и количеству уникальных значений."""
    candidates = [c for c in sheet_meta.columns if c.dtype in _GROUP_PRIORITY]
    if not candidates:
        return None
    candidates.sort(key=lambda c: (_GROUP_PRIORITY.index(c.dtype), c.unique_count))
    return candidates[0].name
