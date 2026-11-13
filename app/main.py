import io
import os
import logging
import time
from typing import Optional

import docx
import fitz  # PyMuPDF
from PIL import Image, UnidentifiedImageError
from zipfile import BadZipFile
from docx.opc.exceptions import PackageNotFoundError
import pytesseract
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status

logger = logging.getLogger(__name__)

# --- Configuración de Tesseract ---
DEFAULT_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def configure_tesseract() -> None:
    """Prioridad: variable TESSERACT_CMD > ruta típica de Windows > PATH del sistema."""
    cmd = os.getenv("TESSERACT_CMD")
    if not cmd and os.name == "nt" and os.path.exists(DEFAULT_WINDOWS_TESSERACT):
        cmd = DEFAULT_WINDOWS_TESSERACT
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


configure_tesseract()

# --- Configuración de idiomas OCR ---
DEFAULT_OCR_LANG = os.getenv("OCR_LANG", "spa+eng")
SUPPORTED_LANGS = {"spa", "eng"}


def normalize_lang(lang: Optional[str]) -> str:
    # En una URL el "+" llega como espacio, por eso se normaliza.
    value = (lang or DEFAULT_OCR_LANG).strip().lower().replace(" ", "+").replace(",", "+")
    parts = [p for p in value.split("+") if p]
    if not parts or any(p not in SUPPORTED_LANGS for p in parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Idioma no soportado. Usa: {', '.join(sorted(SUPPORTED_LANGS))} (combinables con '+')."
        )
    return "+".join(dict.fromkeys(parts))


def run_ocr(image: Image.Image, lang: str) -> str:
    """Comprueba la dependencia externa solo cuando el archivo necesita OCR."""
    try:
        installed = set(pytesseract.get_languages(config=""))
        missing = set(lang.split("+")) - installed
        if missing:
            raise HTTPException(status_code=503, detail=f"Faltan idiomas de Tesseract: {', '.join(sorted(missing))}.")
        return pytesseract.image_to_string(image, lang=lang, timeout=120).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Tesseract no está disponible. Revisa TESSERACT_CMD o PATH.") from exc
    except (pytesseract.TesseractError, RuntimeError) as exc:
        logger.exception("Fallo del motor OCR")
        raise HTTPException(status_code=503, detail="El motor OCR falló o excedió el tiempo de espera.") from exc


app = FastAPI(
    title="Microservicio de OCR y Lectura Accesible - Línea B",
    description="API REST para extracción de texto (OCR, PyMuPDF, python-docx) y lectura accesible.",
    version="0.3.0"
)

# MIME types y extensiones válidas
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg"]
ALLOWED_PDF_TYPES = ["application/pdf"]
ALLOWED_DOCX_TYPES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]


# Endpoint principal de prueba
@app.get("/")
def read_root():
    return {
        "status": "ok",
        "servicio": "Línea B - OCR y Lectura Accesible",
        "mensaje": "Endpoint funcional para imágenes, PDF y DOCX (Sprint 1)"
    }


# Endpoint de verificación de salud de la API
@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/extract", status_code=status.HTTP_200_OK)
def extract_text(
    file: UploadFile = File(...),
    lang: Optional[str] = Query(None, description="spa, eng o spa+eng"),
):
    # FastAPI ejecuta esta función síncrona en un hilo para no bloquear otras peticiones.
    start_time = time.perf_counter()
    ocr_lang = normalize_lang(lang)

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionó ningún archivo válido."
        )

    content_type = file.content_type
    filename = file.filename
    contents = file.file.read()

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo proporcionado está vacío."
        )

    extracted_pages = []
    full_text = []

    # La extensión conocida tiene prioridad; el MIME sirve si no hay extensión reconocida.
    extension = os.path.splitext(filename.lower())[1]
    formats = {".png": "image", ".jpg": "image", ".jpeg": "image", ".pdf": "pdf", ".docx": "docx"}
    file_format = formats.get(extension)
    if file_format is None:
        if content_type in ALLOWED_IMAGE_TYPES:
            file_format = "image"
        elif content_type in ALLOWED_PDF_TYPES:
            file_format = "pdf"
        elif content_type in ALLOWED_DOCX_TYPES:
            file_format = "docx"

    # 1. Procesamiento de IMÁGENES (Tesseract OCR)
    if file_format == "image":
        try:
            with Image.open(io.BytesIO(contents)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise HTTPException(status_code=400, detail="La imagen debe ser PNG o JPEG.")
                clean_text = run_ocr(image, ocr_lang)

            extracted_pages.append({"page": 1, "text": clean_text})
            if clean_text:
                full_text.append(clean_text)

        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, ValueError, fitz.FileDataError,
                BadZipFile, PackageNotFoundError) as exc:
            raise HTTPException(status_code=400, detail="Archivo dañado o contenido inválido para el formato indicado.") from exc
        except Exception as exc:
            logger.exception("Error al extraer texto")
            raise HTTPException(status_code=500, detail="Error interno al procesar el archivo.") from exc

    # 2. Procesamiento de PDF (PyMuPDF + Tesseract fallback)
    elif file_format == "pdf":
        try:
            # El contexto cierra el documento incluso si falla una página.
            with fitz.open(stream=contents, filetype="pdf") as pdf_document:
                if pdf_document.needs_pass:
                    raise HTTPException(status_code=400, detail="El PDF requiere contraseña.")
                for page_index, page in enumerate(pdf_document):
                    page_text = page.get_text("text").strip()
                    # Las páginas sin texto se renderizan en RGB a 300 dpi para OCR.
                    if not page_text:
                        pix = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
                        with Image.frombytes("RGB", [pix.width, pix.height], pix.samples) as image:
                            page_text = run_ocr(image, ocr_lang)
                    extracted_pages.append({"page": page_index + 1, "text": page_text})
                    if page_text:
                        full_text.append(page_text)

        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, ValueError, fitz.FileDataError,
                BadZipFile, PackageNotFoundError) as exc:
            raise HTTPException(status_code=400, detail="Archivo dañado o contenido inválido para el formato indicado.") from exc
        except Exception as exc:
            logger.exception("Error al extraer texto")
            raise HTTPException(status_code=500, detail="Error interno al procesar el archivo.") from exc

    # 3. Procesamiento de WORD / DOCX (python-docx)
    elif file_format == "docx":
        try:
            doc = docx.Document(io.BytesIO(contents))
            paragraphs_text = []

            # Recorre párrafos y tablas en el orden en que aparecen en el documento.
            for block in doc.iter_inner_content():
                if isinstance(block, docx.text.paragraph.Paragraph):
                    if block.text.strip():
                        paragraphs_text.append(block.text.strip())
                else:
                    for row in block.rows:
                        cells = []
                        seen = set()
                        for cell in row.cells:
                            # Una celda combinada puede aparecer varias veces en una fila.
                            if cell._tc not in seen:
                                seen.add(cell._tc)
                                if cell.text.strip():
                                    cells.append(cell.text.strip())
                        if cells:
                            paragraphs_text.append(" | ".join(cells))

            docx_text = "\n".join(paragraphs_text)

            extracted_pages.append({"page": 1, "text": docx_text})
            if docx_text:
                full_text.append(docx_text)

        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, ValueError, fitz.FileDataError,
                BadZipFile, PackageNotFoundError) as exc:
            raise HTTPException(status_code=400, detail="Archivo dañado o contenido inválido para el formato indicado.") from exc
        except Exception as exc:
            logger.exception("Error al extraer texto")
            raise HTTPException(status_code=500, detail="Error interno al procesar el archivo.") from exc

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado ({content_type}). Se admiten PDF, DOCX e imágenes (PNG, JPG)."
        )

    processing_time = round(time.perf_counter() - start_time, 3)

    return {
        "filename": filename,
        "content_type": content_type,
        "total_pages": len(extracted_pages),
        "extracted_text": "\n\n".join(full_text),
        "content_by_page": extracted_pages,
        "metadata": {
            "processing_time_seconds": processing_time,
            "language": ocr_lang,
            "pages_processed": len(extracted_pages)
        }
    }