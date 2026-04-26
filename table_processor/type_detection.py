from __future__ import annotations

import re
from dataclasses import dataclass
from math import log2

import pandas as pd

from table_processor.models import ColumnType

_THRESHOLD = 0.85

_BOOL_VALUES = {"true", "false", "yes", "no", "да", "нет", "1", "0"}

_ID_NAME_KEYWORDS = {
    "инн", "кпп", "огрн", "снилс", "окпо", "октмо", "окато",
    "id", "uuid", "guid", "код", "code", "number", "номер",
    "артикул", "sku", "barcode", "штрихкод", "serial",
    "вэд", "окпд", "оквэд", "реестровый", "кадастровый",
}

_PRICE_NAME_KEYWORDS = {
    "цена", "стоимость", "сумма", "price", "cost", "amount",
    "выручка", "доход", "расход", "бюджет", "тариф",
}

_RE_DATETIME = re.compile(
    r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}[T \t]\d{2}:\d{2}"
    r"(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)
_RE_DATE = re.compile(
    r"^\d{4}[-/\.]\d{2}[-/\.]\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$"
)
_RE_BOOL = re.compile(r"^(true|false|yes|no|да|нет|1|0)$", re.IGNORECASE)


@dataclass
class ColumnProfile:
    """Профиль колонки: все признаки вычисляются один раз
    и передаются в score_column."""

    col_name: str
    total: int
    unique_count: int
    unique_ratio: float
    mean_length: float
    std_length: float
    min_length: int
    max_length: int
    has_leading_zeros: bool
    numeric_ratio: float
    entropy: float
    name_lower: str
    name_has_id_keyword: bool
    name_has_price_keyword: bool

    @classmethod
    def from_series(cls, series: pd.Series, col_name: str) -> ColumnProfile:
        """Вычисляет все признаки профиля из серии pandas."""
        str_vals = series.dropna().astype(str).str.strip()
        str_vals = str_vals[str_vals != ""]
        total = len(str_vals)

        if total == 0:
            name_lower = col_name.lower()
            return cls(
                col_name=col_name,
                total=0,
                unique_count=0,
                unique_ratio=0.0,
                mean_length=0.0,
                std_length=0.0,
                min_length=0,
                max_length=0,
                has_leading_zeros=False,
                numeric_ratio=0.0,
                entropy=0.0,
                name_lower=name_lower,
                name_has_id_keyword=any(kw in name_lower for kw in _ID_NAME_KEYWORDS),
                name_has_price_keyword=any(
                    kw in name_lower for kw in _PRICE_NAME_KEYWORDS
                ),
            )

        unique_count = int(str_vals.nunique())
        unique_ratio = unique_count / total

        lengths = str_vals.str.len()
        mean_length = float(lengths.mean())
        std_length = float(lengths.std(ddof=0)) if total > 1 else 0.0
        min_length = int(lengths.min())
        max_length = int(lengths.max())

        # Ведущие нули: >5% значений начинаются с "0" + цифра
        leading_zero_ratio = str_vals.str.match(r"^0\d+").sum() / total
        name_lower = col_name.lower()
        id_in_name = any(kw in name_lower for kw in {"инн", "кпп", "огрн"})
        has_leading_zeros = leading_zero_ratio >= 0.05 or (
            id_in_name and str_vals.str.startswith("0").any()
        )

        # Доля числовых значений после нормализации разделителей
        normalized = (
            str_vals.str.replace(",", ".", regex=False)
            .str.replace(r"\s+", "", regex=True)
        )
        numeric_ratio = float(
            pd.to_numeric(normalized, errors="coerce").notna().sum() / total
        )

        # Информационная энтропия распределения значений
        value_counts = str_vals.value_counts()
        probs = value_counts / total
        entropy = float(-sum(p * log2(p) for p in probs if p > 0))

        return cls(
            col_name=col_name,
            total=total,
            unique_count=unique_count,
            unique_ratio=unique_ratio,
            mean_length=mean_length,
            std_length=std_length,
            min_length=min_length,
            max_length=max_length,
            has_leading_zeros=has_leading_zeros,
            numeric_ratio=numeric_ratio,
            entropy=entropy,
            name_lower=name_lower,
            name_has_id_keyword=any(kw in name_lower for kw in _ID_NAME_KEYWORDS),
            name_has_price_keyword=any(kw in name_lower for kw in _PRICE_NAME_KEYWORDS),
        )


@dataclass
class TypeScores:
    """Скоры для каждого возможного типа колонки."""

    identifier: float = 0.0
    numeric: float = 0.0
    categorical: float = 0.0
    text: float = 0.0
    mixed: float = 0.0
    empty: float = 0.0

    def winner(self) -> str:
        """Возвращает имя типа с максимальным скором."""
        return max(self.__dict__, key=lambda k: self.__dict__[k])


def score_column(profile: ColumnProfile) -> TypeScores:
    """Вычисляет скоры для каждого типа колонки на основе профиля признаков."""
    scores = TypeScores()

    # Identifier
    s = 0.0
    if profile.name_has_id_keyword:
        s += 0.5
    if profile.has_leading_zeros:
        s += 0.4
    if profile.std_length < 2.0 and profile.min_length >= 5:
        s += 0.3
    if profile.unique_ratio > 0.8:
        s += 0.2
    if profile.numeric_ratio > 0.85 and profile.mean_length >= 8:
        s += 0.2
    if profile.name_has_price_keyword:
        s -= 0.4
    scores.identifier = max(0.0, min(1.0, s))

    # Numeric
    s = 0.0
    if profile.numeric_ratio > 0.85:
        s += 0.6
    if profile.name_has_price_keyword:
        s += 0.2
    if profile.mean_length < 15:
        s += 0.1
    if profile.name_has_id_keyword:
        s -= 0.5
    if profile.has_leading_zeros:
        s -= 0.4
    if profile.std_length < 1.0 and profile.min_length >= 8:
        s -= 0.3
    scores.numeric = max(0.0, min(1.0, s))

    # Categorical
    s = 0.0
    if profile.unique_ratio < 0.05:
        s += 0.7
    if profile.unique_ratio < 0.1 and profile.unique_count < 50:
        s += 0.5
    if profile.unique_count < 20:
        s += 0.2
    if profile.unique_ratio > 0.5:
        s -= 0.3
    scores.categorical = max(0.0, min(1.0, s))

    # Text
    s = 0.0
    if profile.mean_length > 50:
        s += 0.5
    if profile.mean_length > 20 and profile.unique_ratio > 0.7:
        s += 0.3
    if profile.numeric_ratio < 0.1:
        s += 0.2
    if profile.name_has_id_keyword:
        s -= 0.3
    scores.text = max(0.0, min(1.0, s))

    # Mixed
    s = 0.0
    if 0.15 < profile.numeric_ratio < 0.85:
        s += 0.6
    if profile.name_has_id_keyword:
        s -= 0.3
    scores.mixed = max(0.0, min(1.0, s))

    return scores


def detect_column_type(series: pd.Series, col_name: str = "") -> ColumnType:
    """Определяет тип колонки: сначала быстрые regex-проверки,
    затем скоринг профиля."""
    non_null = series.dropna()
    if non_null.empty:
        return ColumnType.EMPTY

    str_vals = non_null.astype(str).str.strip()
    str_vals = str_vals[str_vals != ""]
    total = len(str_vals)
    if total == 0:
        return ColumnType.EMPTY

    # Быстрые regex-проверки для однозначных типов
    if str_vals.str.match(_RE_BOOL).sum() / total >= _THRESHOLD:
        return ColumnType.BOOLEAN
    if str_vals.str.match(_RE_DATETIME).sum() / total >= _THRESHOLD:
        return ColumnType.DATETIME
    if str_vals.str.match(_RE_DATE).sum() / total >= _THRESHOLD:
        return ColumnType.DATE

    # Скоринг профиля для остальных типов; для больших серий берём случайную выборку
    profile_series = (
        series.dropna().sample(5000, random_state=42)
        if series.dropna().shape[0] > 5000
        else series
    )
    profile = ColumnProfile.from_series(profile_series, col_name)
    scores = score_column(profile)
    winner = scores.winner()

    if winner == "identifier":
        return ColumnType.TEXT
    if winner == "numeric":
        # Определяем INTEGER vs FLOAT по наличию дробной части
        normalized = (
            str_vals.str.replace(",", ".", regex=False)
            .str.replace(r"\s+", "", regex=True)
        )
        has_decimal = normalized.str.contains(r"\.", regex=True).any()
        return (
            ColumnType.FLOAT
            if (profile.numeric_ratio > 0.85 and has_decimal)
            else ColumnType.INTEGER
        )
    if winner == "categorical":
        return ColumnType.CATEGORICAL
    if winner == "mixed":
        return ColumnType.MIXED
    if winner == "empty":
        return ColumnType.EMPTY
    return ColumnType.TEXT
