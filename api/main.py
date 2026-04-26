from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from table_processor import ChunkStrategy, ProcessingResult, process_file

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

app = FastAPI(title="Table-Aware Processor", version="2.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process", response_model=ProcessingResult)
async def process(
    file: UploadFile = File(...),
    strategy: ChunkStrategy = Query(default=ChunkStrategy.AUTO),
    chunk_size: int = Query(default=50, ge=1, le=1000),
    max_cells_per_chunk: int = Query(default=10_000, ge=100, le=1_000_000),
    max_bytes_per_chunk: int | None = Query(
        default=None, ge=1000, description="Максимальный размер чанка в байтах"
    ),
) -> ProcessingResult:
    """Принимает табличный файл, возвращает ProcessingResult с чанками."""
    original_name = file.filename or "upload"
    _, suffix = os.path.splitext(original_name)

    # Проверка расширения до сохранения файла
    if suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат '{suffix}'. Допустимые: {supported}",
        )

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        return process_file(
            tmp_path,
            strategy=strategy,
            chunk_size=chunk_size,
            max_cells_per_chunk=max_cells_per_chunk,
            display_name=original_name,
            max_bytes_per_chunk=max_bytes_per_chunk,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
