from __future__ import annotations

from pathlib import Path

import chardet
import openpyxl
import pandas as pd

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def detect_encoding(file_path: Path) -> str:
    """Определяет кодировку файла по первым 50 000 байтам."""
    with open(file_path, "rb") as f:
        raw = f.read(50_000)
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def detect_separator(file_path: Path, encoding: str) -> str:
    """Определяет разделитель CSV по первой строке — выбирает наиболее часто встречающийся."""
    with open(file_path, encoding=encoding, errors="replace") as f:
        first_line = f.readline()
    candidates = {",": first_line.count(","), ";": first_line.count(";"), "\t": first_line.count("\t")}
    return max(candidates, key=lambda sep: candidates[sep])


def has_merged_cells(file_path: Path, sheet_name: str) -> bool:
    """Проверяет наличие объединённых ячеек на листе через openpyxl."""
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb[sheet_name]
        return bool(ws.merged_cells.ranges)
    except Exception:
        return False


def load_csv(file_path: Path, display_name: str | None = None) -> dict[str, pd.DataFrame]:
    """Загружает CSV с автоопределением кодировки и разделителя."""
    encoding = detect_encoding(file_path)
    sep = detect_separator(file_path, encoding)
    df = pd.read_csv(file_path, sep=sep, encoding=encoding, dtype=str)
    df = df.reset_index(drop=True)
    key = Path(display_name).stem if display_name else file_path.stem
    return {key: df}


def load_xlsx(file_path: Path) -> dict[str, pd.DataFrame]:
    """Загружает все листы Excel-файла; удаляет полностью пустые строки и колонки."""
    engine = "openpyxl" if file_path.suffix.lower() == ".xlsx" else "xlrd"
    sheets: dict[str, pd.DataFrame] = pd.read_excel(
        file_path, sheet_name=None, dtype=str, engine=engine
    )
    result: dict[str, pd.DataFrame] = {}
    for name, df in sheets.items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        df = df.reset_index(drop=True)
        result[name] = df
    return result


def load_file(file_path: str | Path, display_name: str | None = None) -> dict[str, pd.DataFrame]:
    """Главная функция загрузки файла. Определяет формат и вызывает нужный загрузчик."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Неподдерживаемый формат '{ext}'. Допустимые форматы: {supported}")
    if ext == ".csv":
        return load_csv(path, display_name)
    return load_xlsx(path)
