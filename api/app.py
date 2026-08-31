import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from llm_client import create_llm_client
from pdf_extract import extract_pdf_text, MIN_TEXT_CHARS

API_KEY = os.environ.get("API_KEY", "").strip()
MAX_PDF_BYTES = 15 * 1024 * 1024

llm_client = None


def check_key(x_api_key: str | None) -> None:
    if not API_KEY:
        return
    if (x_api_key or "") != API_KEY:
        raise HTTPException(status_code=401, detail="Неверный API-ключ")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global llm_client
    llm_client = create_llm_client()
    try:
        await llm_client.ensure_model()
    except Exception as exc:
        if llm_client is not None:
            llm_client.status.update(state="error", ready=False, error=str(exc))
    yield


app = FastAPI(
    title="GU-23 analyze",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def index():
    return FileResponse("templates/index.html")


@app.get("/v1/health")
async def health():
    if llm_client is None:
        return {"ok": False, "error": "client not initialized"}
    return {
        "ok": llm_client.status.get("ready") is True and not llm_client.status.get("error"),
        **llm_client.status,
    }


def scan_response(extract: dict, extract_time_ms: float) -> dict:
    message = "В PDF почти нет текста — похоже на скан."
    if extract.get("ocr_error"):
        message += f" OCR не сработал: {extract['ocr_error']}"
    elif extract.get("ocr_used"):
        message += " OCR тоже почти ничего не прочитал."
    else:
        message += " OCR не дал достаточно текста."

    return {
        "ok": False,
        "decision": None,
        "reply_text": None,
        "needs_ocr": True,
        "error": "scan_or_empty",
        "message": message,
        "extracted": {
            "legal_entity": "",
            "station": "",
            "act_number": "",
            "act_date": "",
            "wagons": [],
            "reason_quote": "",
        },
        "debug": {
            "page_count": extract["page_count"],
            "char_count": extract["char_count"],
            "letter_count": extract["letter_count"],
            "ocr_used": extract.get("ocr_used", False),
            "ocr_error": extract.get("ocr_error") or "",
            "extract_time_ms": round(extract_time_ms, 2),
            "model": llm_client.status.get("model") if llm_client else None,
        },
    }


async def run_classify(text: str) -> dict:
    if llm_client is None:
        raise HTTPException(status_code=503, detail="Клиент не инициализирован")
    if not llm_client.status.get("ready"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "model_not_ready",
                "state": llm_client.status.get("state"),
                "progress": llm_client.status.get("progress"),
                "message": llm_client.status.get("error") or "Модель ещё загружается",
            },
        )
    start = time.perf_counter()
    try:
        result = await llm_client.classify_text(text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "classify_failed", "message": str(exc)},
        ) from exc
    classify_time_ms = (time.perf_counter() - start) * 1000
    result.setdefault("debug", {})["classify_time_ms"] = round(classify_time_ms, 2)
    return result


@app.post("/v1/analyze")
async def analyze(
    file: UploadFile | None = File(default=None),
    x_api_key: str | None = Header(default=None),
):
    check_key(x_api_key)
    if file is None:
        raise HTTPException(status_code=400, detail="Ожидается файл PDF в поле file")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not (filename.endswith(".pdf") or "pdf" in content_type):
        raise HTTPException(status_code=400, detail="Нужен PDF")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF больше 15 МБ")

    start_extract = time.perf_counter()
    try:
        extract = extract_pdf_text(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать PDF: {exc}") from exc
    extract_time_ms = (time.perf_counter() - start_extract) * 1000

    if extract["letter_count"] < MIN_TEXT_CHARS:
        return scan_response(extract, extract_time_ms)

    result = await run_classify(extract["text"])
    result.setdefault("debug", {})
    result["debug"]["extract_time_ms"] = round(extract_time_ms, 2)
    result["debug"]["ocr_used"] = extract.get("ocr_used", False)
    return result
