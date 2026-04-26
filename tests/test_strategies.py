import math
import re
from pathlib import Path

import pandas as pd
import pytest

from table_processor.analyzer import analyze_sheet
from table_processor.models import ChunkStrategy, ColumnType
from table_processor.strategies.row_based import RowBasedStrategy
from table_processor.strategies.semantic import SemanticStrategy
from table_processor.type_detection import detect_column_type

# Фиктивный путь — нужен только для генерации chunk_id и filename
_SOURCE = Path("test_file.xlsx")


@pytest.fixture
def categorical_df() -> pd.DataFrame:
    # 75 строк: по 25 на каждый отдел, уникальные сотрудники, числовая выручка
    departments = ["Финансы"] * 25 + ["Продажи"] * 25 + ["HR"] * 25
    employees = [f"Сотрудник_{i}" for i in range(75)]
    revenues = [f"{15000 + i * 100}.50" for i in range(75)]
    return pd.DataFrame(
        {"Отдел": departments, "Сотрудник": employees, "Выручка": revenues}
    )


@pytest.fixture
def numeric_only_df() -> pd.DataFrame:
    # 10 строк, только числовые колонки — нет категориальных
    return pd.DataFrame({
        "Показатель1": [str(i) for i in range(1, 11)],
        "Показатель2": [f"{i * 100.5:.1f}" for i in range(1, 11)],
        "Показатель3": [str(i * 1000) for i in range(1, 11)],
    })


def test_row_based_chunk_count(categorical_df):
    # ceil(75 / 10) = 8 чанков
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = RowBasedStrategy(chunk_size=10).split(categorical_df, meta, _SOURCE)
    assert len(chunks) == math.ceil(75 / 10)


def test_row_based_last_chunk_rows(categorical_df):
    # Последний чанк: 75 % 10 = 5 строк
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = RowBasedStrategy(chunk_size=10).split(categorical_df, meta, _SOURCE)
    assert chunks[-1].row_count == 5


def test_row_based_strategy_type(categorical_df):
    # Все чанки имеют стратегию ROW_BASED
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = RowBasedStrategy(chunk_size=10).split(categorical_df, meta, _SOURCE)
    assert all(c.strategy == ChunkStrategy.ROW_BASED for c in chunks)


def test_row_based_source_ref_format(categorical_df):
    # source_ref первого чанка соответствует формату Sheet!A{n}:{col}{m}
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = RowBasedStrategy(chunk_size=10).split(categorical_df, meta, _SOURCE)
    assert re.match(r"^.+!A\d+:[A-Z]+\d+$", chunks[0].source_ref)


def test_row_based_max_bytes(categorical_df):
    # С max_bytes_per_chunk=500 первый чанк содержит меньше строк чем при chunk_size=50
    meta = analyze_sheet(categorical_df, "Тест")
    chunks_default = RowBasedStrategy(chunk_size=50).split(
        categorical_df, meta, _SOURCE
    )
    chunks_bytes = RowBasedStrategy(max_bytes_per_chunk=500).split(
        categorical_df, meta, _SOURCE
    )
    assert chunks_bytes[0].row_count < chunks_default[0].row_count


def test_semantic_groups_by_categorical(categorical_df):
    # SemanticStrategy на categorical_df даёт ровно 3 чанка — по одному на отдел
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = SemanticStrategy().split(categorical_df, meta, _SOURCE)
    assert len(chunks) == 3


def test_semantic_chunk_ids_contain_group_value(categorical_df):
    # chunk_id каждого семантического чанка содержит значение группы
    meta = analyze_sheet(categorical_df, "Тест")
    chunks = SemanticStrategy().split(categorical_df, meta, _SOURCE)
    group_values = {"Финансы", "Продажи", "HR"}
    for chunk in chunks:
        assert any(val in chunk.id for val in group_values)


def test_semantic_fallback_to_row_based(numeric_only_df):
    # На числовых данных нет категориальной колонки → откат к ROW_BASED
    meta = analyze_sheet(numeric_only_df, "Тест")
    chunks = SemanticStrategy().split(numeric_only_df, meta, _SOURCE)
    assert all(c.strategy == ChunkStrategy.ROW_BASED for c in chunks)


def test_semantic_respects_chunk_size():
    # chunk_size корректно сохраняется в атрибуте стратегии
    strategy = SemanticStrategy(chunk_size=123)
    assert strategy._chunk_size == 123


def test_detect_inn_as_text():
    # Колонка ИНН с 10-значными числами определяется как TEXT (идентификатор)
    series = pd.Series([str(7724496523 + i) for i in range(20)])
    assert detect_column_type(series, "ИНН заказчика") == ColumnType.TEXT


def test_detect_price_as_float():
    # Колонка Цена с дробными значениями определяется как FLOAT
    series = pd.Series([f"{150000.50 + i * 100:.2f}" for i in range(20)])
    assert detect_column_type(series, "Цена") == ColumnType.FLOAT


def test_detect_date_column():
    # Значения в формате YYYY-MM-DD определяются как DATE
    series = pd.Series([f"2024-{m:02d}-15" for m in range(1, 13)])
    assert detect_column_type(series, "Дата") == ColumnType.DATE
