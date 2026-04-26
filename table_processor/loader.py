from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

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
    """Определяет разделитель CSV по первой строке —
    выбирает наиболее часто встречающийся."""
    with open(file_path, encoding=encoding, errors="replace") as f:
        first_line = f.readline()
    candidates = {
        ",": first_line.count(","),
        ";": first_line.count(";"),
        "\t": first_line.count("\t"),
    }
    return max(candidates, key=lambda sep: candidates[sep])


def has_merged_cells(file_path: Path, sheet_name: str) -> bool:
    """Проверяет наличие объединённых ячеек
    через прямое чтение XML из ZIP-архива xlsx."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            # Читаем workbook.xml чтобы сопоставить имя листа с его XML-файлом
            wb_xml = zf.read("xl/workbook.xml")
            root = ElementTree.fromstring(wb_xml)
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_elem = next(
                (
                    s for s in root.findall(".//x:sheet", ns)
                    if s.get("name") == sheet_name
                ),
                None,
            )
            if sheet_elem is None:
                return False
            # sheetId соответствует номеру файла sheet{N}.xml
            sheet_id = sheet_elem.get("sheetId", "1")
            sheet_xml = zf.read(f"xl/worksheets/sheet{sheet_id}.xml")
            return b"<mergeCell" in sheet_xml
    except Exception:
        return False


def load_csv(
    file_path: Path, display_name: str | None = None
) -> dict[str, pd.DataFrame]:
    """Загружает CSV с автоопределением кодировки и разделителя."""
    encoding = detect_encoding(file_path)
    sep = detect_separator(file_path, encoding)
    df = pd.read_csv(file_path, sep=sep, encoding=encoding, dtype=str)
    df = df.reset_index(drop=True)
    key = Path(display_name).stem if display_name else file_path.stem
    return {key: df}


def _find_header_row(file_path: Path, sheet_name: str) -> int:
    """Ищет первую строку где заполнено более 30% ячеек;
    возвращает 0-based индекс или 0."""
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb[sheet_name]
        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if not row:
                continue
            filled = sum(
                1 for cell in row
                if cell is not None and str(cell).strip() != ""
            )
            if filled / len(row) > 0.3:
                return row_idx
        return 0
    except Exception:
        return 0


def load_xlsx(file_path: Path) -> dict[str, pd.DataFrame]:
    """Загружает все листы Excel-файла; удаляет полностью пустые строки и колонки."""
    engine = "openpyxl" if file_path.suffix.lower() == ".xlsx" else "xlrd"
    is_xlsx = file_path.suffix.lower() == ".xlsx"
    result: dict[str, pd.DataFrame] = {}
    with pd.ExcelFile(file_path, engine=engine) as xf:
        for name in xf.sheet_names:
            # Для .xlsx определяем строку заголовка и читаем сразу с нужным header
            header_row = _find_header_row(file_path, name) if is_xlsx else 0
            df = xf.parse(name, dtype=str, header=header_row)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            df = df.reset_index(drop=True)
            result[name] = df
    return result


def load_file(
    file_path: str | Path, display_name: str | None = None
) -> dict[str, pd.DataFrame]:
    """Главная функция загрузки файла. Определяет формат и вызывает нужный загрузчик."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Неподдерживаемый формат '{ext}'. Допустимые форматы: {supported}"
        )
    if ext == ".csv":
        return load_csv(path, display_name)
    return load_xlsx(path)
