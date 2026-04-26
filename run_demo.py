import json
import time
from pathlib import Path

from table_processor import ChunkStrategy, process_file

EXAMPLES_DIR = Path("examples")
OUTPUT_DIR = Path("output")

SCENARIOS = [
    {
        "name": "Маленький файл, стратегия AUTO",
        "file": "small_analytical.xlsx",
        "kwargs": {"strategy": ChunkStrategy.AUTO},
    },
    {
        "name": "Средний файл, стратегия AUTO",
        "file": "medium_registry.xlsx",
        "kwargs": {"strategy": ChunkStrategy.AUTO},
    },
    {
        "name": "Стресс-тест, стратегия ROW_BASED",
        "file": "stress_lots.xlsx",
        "kwargs": {"strategy": ChunkStrategy.ROW_BASED, "chunk_size": 100},
    },
    {
        "name": "Стресс-тест, байтовая нарезка",
        "file": "stress_lots.xlsx",
        "kwargs": {"strategy": ChunkStrategy.ROW_BASED, "max_bytes_per_chunk": 50000},
    },
]


def run_demo() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for scenario in SCENARIOS:
        name = scenario["name"]
        file = scenario["file"]
        kwargs = scenario["kwargs"]

        print(f"\n=== {name} ===")

        start = time.perf_counter()
        result = process_file(EXAMPLES_DIR / file, **kwargs)
        elapsed = time.perf_counter() - start

        print(f"  Файл:     {result.filename}")
        print(f"  Стратегия:{result.strategy.value}")
        print(f"  Листов:   {result.sheet_count}")
        print(f"  Строк:    {result.total_rows}")
        print(f"  Чанков:   {result.total_chunks}")
        print(f"  Время:    {elapsed:.3f} с")

        if result.warnings:
            for warning in result.warnings:
                print(f"  [!] {warning}")

        # Сохраняем результат в JSON: индекс + имя файла + стратегия для уникальности
        scenario_idx = SCENARIOS.index(scenario)
        stem = Path(file).stem
        strategy_val = result.strategy.value
        out_path = OUTPUT_DIR / f"{scenario_idx + 1}_{stem}_{strategy_val}.json"
        out_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"\n✓ Все результаты сохранены в {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_demo()
