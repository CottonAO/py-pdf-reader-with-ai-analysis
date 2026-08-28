from io import BytesIO
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_bytes

MIN_TEXT_CHARS = 80

def extract_pdf_text(data: bytes, use_ocr: bool = True) -> dict:
    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append((page.extract_text() or "").strip())

    text = "\n\n".join(part for part in pages if part).strip()
    letters = sum(1 for ch in text if ch.isalpha())
    looks_like_scan = letters < MIN_TEXT_CHARS
    ocr_used = False

    if looks_like_scan and use_ocr:
        try:
            # Рендерим страницы PDF в изображения
            images = convert_from_bytes(data, dpi=300)
            ocr_pages = []
            for img in images:
                page_text = pytesseract.image_to_string(img, lang="rus+eng")
                ocr_pages.append(page_text.strip())
            ocr_text = "\n\n".join(p for p in ocr_pages if p).strip()
            ocr_letters = sum(1 for ch in ocr_text if ch.isalpha())
            if ocr_letters > letters:  # OCR дал больше текста
                text = ocr_text
                letters = ocr_letters
                pages = ocr_pages
                ocr_used = True
        except Exception:
            # OCR не удался, оставляем исходный (пустой) текст
            pass

    return {
        "text": text,
        "page_count": len(reader.pages),
        "char_count": len(text),
        "letter_count": letters,
        "looks_like_scan": looks_like_scan,
        "ocr_used": ocr_used,
        "pages": pages,
    }