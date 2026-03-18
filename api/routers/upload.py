"""CSV upload router for QueryMind API.

Allows users to upload a CSV file and returns metadata + preview rows.
"""

from __future__ import annotations

import csv
import io
from typing import List, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api.schemas import CsvUploadResponse

router = APIRouter(prefix="/api/v1", tags=["upload"])

MAX_CSV_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
}


@router.post("/upload-csv", response_model=CsvUploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> CsvUploadResponse:
    """Upload and parse a CSV file, returning summary metadata and a row preview."""
    filename = file.filename or "uploaded.csv"

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are supported.",
        )

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type: {file.content_type}",
        )

    raw = await file.read()
    size_bytes = len(raw)
    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if size_bytes > MAX_CSV_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is too large. Max supported size is 5MB.",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode CSV. Please upload UTF-8 or Latin-1 text.",
            ) from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    if not columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV has no header row.",
        )

    preview_rows: List[Dict[str, str]] = []
    row_count = 0
    for row in reader:
        row_count += 1
        if len(preview_rows) < 8:
            preview_rows.append({k: str(v or "") for k, v in row.items()})

    return CsvUploadResponse(
        file_name=filename,
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        preview_rows=preview_rows,
    )
