from __future__ import annotations

from pathlib import Path

import pandas as pd

from table_processor.loader import has_merged_cells
from table_processor.models import ColumnMeta, ColumnType, SheetMeta
from table_processor.type_detection import detect_column_type
from table_processor.utils import make_source_ref as _make_source_ref


def _get_numeric_stats(series: pd.Series) -> dict | None:
    """Считает min, max, mean для колонки через pd.to_numeric;
    возвращает None если не получилось."""
    numeric = pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    valid = numeric.dropna()
    if valid.empty:
        return None
    return {
        "min_value": float(valid.min()),
        "max_value": float(valid.max()),
        "mean_value": float(valid.mean()),
    }


def _get_sample_values(series: pd.Series, n: int = 5) -> list:
    """Возвращает до n уникальных непустых значений из колонки."""
    non_null = series.dropna()
    unique_vals = non_null.drop_duplicates()
    return [str(v) for v in unique_vals.iloc[:n]]


def _get_top_values(series: pd.Series, n: int = 5) -> dict[str, int]:
    """Возвращает top-n значений с частотами для строковых и категориальных колонок."""
    counts = series.dropna().astype(str).value_counts().head(n)
    return {str(k): int(v) for k, v in counts.items()}


def _detect_header_rows(df: pd.DataFrame) -> int:
    """Определяет количество строк шапки: 1 или 2."""
    if len(df) < 2:
        return 1
    first_row = df.iloc[0].astype(str)
    second_row = df.iloc[1]

    # Если вторая строка более чем наполовину пустая — двойная шапка
    empty_ratio = second_row.isna().sum() / len(second_row)
    if empty_ratio > 0.5:
        return 2

    # Если все непустые значения второй строки присутствуют в первой — двойная шапка
    second_non_null = second_row.dropna().astype(str)
    if not second_non_null.empty and all(
        v in first_row.values for v in second_non_null
    ):
        return 2

    return 1


def _build_sheet_warnings(
    df: pd.DataFrame,
    columns_meta: list[ColumnMeta],
) -> list[str]:
    """Собирает предупреждения на уровне листа:
    пустые строки, смешанные типы, подозрительные итоги."""
    warnings: list[str] = []

    # Предупреждение о большом количестве пустых строк
    empty_row_ratio = df.isna().all(axis=1).sum() / len(df) if len(df) > 0 else 0.0
    if empty_row_ratio > 0.2:
        warnings.append(f"Много пустых строк: {round(empty_row_ratio * 100)}%")

    # Предупреждение о колонках со смешанными типами
    mixed_cols = [c.name for c in columns_meta if c.dtype == ColumnType.MIXED]
    if mixed_cols:
        warnings.append(f"Смешанные типы в колонках: {', '.join(mixed_cols)}")

    # Предупреждение о подозрительных итогах в последней строке
    if len(df) > 1:
        last_row = df.iloc[-1]
        for col_meta in columns_meta:
            if col_meta.mean_value is None or col_meta.name not in df.columns:
                continue
            last_val = pd.to_numeric(last_row.get(col_meta.name), errors="coerce")
            if pd.notna(last_val) and col_meta.mean_value > 0:
                if last_val > col_meta.mean_value * 3:
                    warnings.append("Подозрительные итоги в последней строке")
                    break

    return warnings


def analyze_sheet(
    df: pd.DataFrame,
    sheet_name: str,
    file_path: Path | None = None,
) -> SheetMeta:
    """Анализирует один лист: строит метаданные колонок,
    определяет шапку, собирает предупреждения."""
    row_count, col_count = df.shape
    columns_meta: list[ColumnMeta] = []

    for col_name in df.columns:
        series = df[col_name]
        dtype = detect_column_type(series, str(col_name))

        null_ratio = series.isna().sum() / len(series) if len(series) > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))
        sample_values = _get_sample_values(series)

        top_values: dict[str, int] = {}
        if dtype in (ColumnType.TEXT, ColumnType.CATEGORICAL, ColumnType.MIXED):
            top_values = _get_top_values(series)

        stats = (
            _get_numeric_stats(series)
            if dtype in (ColumnType.INTEGER, ColumnType.FLOAT)
            else None
        )
        columns_meta.append(
            ColumnMeta(
                name=str(col_name),
                dtype=dtype,
                null_ratio=round(null_ratio, 4),
                unique_count=unique_count,
                sample_values=sample_values,
                top_values=top_values,
                min_value=stats["min_value"] if stats else None,
                max_value=stats["max_value"] if stats else None,
                mean_value=stats["mean_value"] if stats else None,
            )
        )

    header_rows = _detect_header_rows(df)
    source_ref = _make_source_ref(sheet_name, row_count, col_count)

    # Проверяем объединённые ячейки только для .xlsx
    merged = False
    if file_path is not None and file_path.suffix.lower() == ".xlsx":
        merged = has_merged_cells(file_path, sheet_name)

    warnings = _build_sheet_warnings(df, columns_meta)
    if merged:
        warnings.append("Обнаружены объединённые ячейки")

    return SheetMeta(
        name=sheet_name,
        row_count=row_count,
        col_count=col_count,
        columns=columns_meta,
        header_rows=header_rows,
        has_merged_cells=merged,
        source_ref=source_ref,
        warnings=warnings,
    )


def analyze_file(
    sheets: dict[str, pd.DataFrame],
    file_path: Path | None = None,
) -> dict[str, SheetMeta]:
    """Анализирует все листы файла, возвращает словарь имя листа → SheetMeta."""
    return {name: analyze_sheet(df, name, file_path) for name, df in sheets.items()}
