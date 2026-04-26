# Table-Aware Processor

Python-модуль для обработки табличных файлов (`.xlsx`, `.xls`, `.csv`) с сохранением структуры и умным чанкингом для RAG-систем.

В отличие от обычного чанкинга по символам, модуль режет таблицу по строкам — каждый чанк сохраняет имя листа, заголовки колонок, типы данных и ссылку на исходный диапазон в Excel-нотации.

## Возможности

- Чтение `.xlsx`, `.xls`, `.csv` с автоопределением кодировки и разделителя
- Автопоиск строки начала таблицы (пропуск мета-информации)
- Умное определение типов колонок через скоринг признаков — корректно распознаёт ИНН, КПП, ОГРН как `text`, цены как `float`, регионы как `categorical`
- Три стратегии чанкинга: `row_based`, `semantic`, `auto`
- Три способа ограничения размера чанка: по строкам, по ячейкам, по байтам
- Профилирование колонок: типы, пропуски, статистика, top-N значений
- Предупреждения: смешанные типы, пустые строки, подозрительные итоги, merged cells
- HTTP API на FastAPI

## Установка

Требуется Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Использование

### Как библиотека

```python
from table_processor import process_file, ChunkStrategy

result = process_file(
    "data.xlsx",
    strategy=ChunkStrategy.AUTO,
    chunk_size=50,
)

print(f"Стратегия: {result.strategy}")
print(f"Всего чанков: {result.total_chunks}")

for chunk in result.chunks:
    print(f"{chunk.id} | {chunk.source_ref} | строк: {chunk.row_count}")
```

### Через HTTP API

Запуск сервера:

```bash
uvicorn api.main:app --reload --port 8005
```

Документация Swagger: <http://localhost:8005/docs>

Пример запроса через curl:

```bash
curl -X POST "http://localhost:8005/process?strategy=auto&chunk_size=100" \
  -F "file=@data.xlsx"
```

### Демо на трёх наборах данных

```bash
python run_demo.py
```

Скрипт обрабатывает три файла из `examples/` четырьмя сценариями (auto, row_based с разным chunk_size, байтовая нарезка) и сохраняет результаты в `output/`.

## Структура проекта

```
table_processor/        — основной модуль
├── models.py           — Pydantic-модели
├── loader.py           — загрузка файлов
├── analyzer.py         — анализ листов
├── type_detection.py   — определение типов через скоринг
├── processor.py        — главный фасад
├── utils.py            — Excel-нотация
└── strategies/
    ├── base.py         — абстрактный класс
    ├── row_based.py    — нарезка по строкам
    └── semantic.py     — нарезка по группам

api/main.py             — FastAPI приложение
tests/                  — pytest, 18 тестов
examples/               — три тестовых файла
output/                 — примеры JSON-результатов
run_demo.py             — демо-скрипт
CONTRACT.md             — описание формата JSON
```

## Параметры обработки

| Параметр | Дефолт | Описание |
|---|---|---|
| `strategy` | `auto` | `row_based`, `semantic` или `auto` |
| `chunk_size` | `50` | Максимум строк в чанке |
| `max_cells_per_chunk` | `10000` | Защита от широких таблиц |
| `max_bytes_per_chunk` | `None` | Нарезка по байтам |

## Стратегии чанкинга

**`row_based`** — простая нарезка по N строк. Подходит когда нет естественных группировок.

**`semantic`** — группировка по значениям категориальной или датовой колонки. Колонка для группировки выбирается автоматически по приоритету: categorical → date → datetime → boolean.

**`auto`** — модуль сам выбирает стратегию: если найдена подходящая колонка для группировки — semantic, иначе row_based.

## Тесты и линтинг

```bash
pytest tests/ -v
ruff check .
```

18 тестов покрывают загрузку файлов, определение типов, нарезку по строкам и группам, генерацию `source_ref`.

## Демо результаты

На реальных файлах:

| Файл | Строк | Колонок | Стратегия | Чанков | Время |
|---|---|---|---|---|---|
| small_analytical.xlsx | 52 | 47 | semantic | 2 | 0.3с |
| medium_registry.xlsx | 92 123 | 19 | row_based | 1775 | 21.7с |
| stress_lots.xlsx | 99 999 | 13 | row_based | 1000 | 14.8с |
| stress_lots.xlsx (байты) | 99 999 | 13 | row_based | 794 | 18.1с |

## Контракт JSON

Полное описание формата выходных данных — в [CONTRACT.md](CONTRACT.md).

## Стек

Python 3.10+ · pandas · openpyxl · xlrd · pydantic · FastAPI · uvicorn · pytest · ruff
