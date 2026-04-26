
import pandas as pd
import pytest

from table_processor.loader import load_file


def test_csv_comma_separator(tmp_path):
    # CSV с запятой и UTF-8 — колонки и строки читаются корректно
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "Название,Количество,Цена\nТовар1,10,100.50\nТовар2,20,200.00\n",
        encoding="utf-8",
    )
    sheets = load_file(csv_file)
    df = next(iter(sheets.values()))
    assert list(df.columns) == ["Название", "Количество", "Цена"]
    assert len(df) == 2


def test_csv_semicolon_separator(tmp_path):
    # CSV с точкой с запятой и кодировкой cp1251
    csv_file = tmp_path / "test_semi.csv"
    lines = [
        "Регион;Выручка;Клиент",
        "Москва;150000;ООО Альфа",
        "Санкт-Петербург;200000;ЗАО Бета",
        "Казань;120000;ИП Гамма",
        "Новосибирск;180000;АО Дельта",
        "Екатеринбург;130000;ООО Эпсилон",
    ]
    csv_file.write_bytes("\n".join(lines).encode("cp1251"))
    sheets = load_file(csv_file)
    df = next(iter(sheets.values()))
    assert "Регион" in df.columns
    assert len(df) == 5


def test_xlsx_multiple_sheets(tmp_path):
    # XLSX с двумя листами: возвращается словарь с двумя ключами, оба с данными
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"A": [1, 2], "B": [3, 4]}).to_excel(
            writer, sheet_name="Лист1", index=False
        )
        pd.DataFrame({"X": [5, 6], "Y": [7, 8]}).to_excel(
            writer, sheet_name="Лист2", index=False
        )
    sheets = load_file(path)
    assert len(sheets) == 2
    assert "Лист1" in sheets and "Лист2" in sheets
    assert len(sheets["Лист1"]) > 0
    assert len(sheets["Лист2"]) > 0


def test_xlsx_header_autodetect(tmp_path):
    # Первые 3 строки — мета-информация; 4-я строка — настоящий заголовок таблицы
    import openpyxl

    path = tmp_path / "header_test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    # 4 колонки: 1 заполненная в метастроке = 25% < порога 30% → не считается заголовком
    ws.append(["Отчёт за 2024 год"])  # строка 1: одна ячейка из четырёх
    ws.append([None])                 # строка 2: пустая
    ws.append([None])                 # строка 3: пустая
    ws.append(["Товар", "Цена", "Количество", "Склад"])  # строка 4: заголовок
    ws.append(["Яблоки", "50.00", "100", "А1"])
    ws.append(["Груши", "60.00", "200", "Б2"])
    ws.append(["Апельсины", "70.00", "150", "В3"])
    wb.save(path)

    sheets = load_file(path)
    df = next(iter(sheets.values()))
    # Колонки должны содержать имена из строки-заголовка, а не Unnamed
    assert "Товар" in df.columns
    assert not any("Unnamed" in str(c) for c in df.columns)


def test_missing_file_raises(tmp_path):
    # Несуществующий путь → FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_file(tmp_path / "no_such_file.xlsx")


def test_unsupported_format_raises(tmp_path):
    # Файл с расширением .json → ValueError
    json_file = tmp_path / "data.json"
    json_file.write_text("{}")
    with pytest.raises(ValueError):
        load_file(json_file)
