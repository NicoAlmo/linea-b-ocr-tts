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
from fastapi.responses import Response
from gtts import gTTS, gTTSError

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

# Tesseract usa spa/eng; el motor de voz usa es/en.
SUPPORTED_TTS_LANGS = {"es", "en"}
MAX_TTS_CHARACTERS = 20_000


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
    description="API REST para extraer texto de imágenes, PDF y DOCX y convertirlo a voz MP3 mediante gTTS (requiere Internet).",
    version="0.4.0"
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
        "mensaje": "Extracción de texto en /extract y generación de voz MP3 en /extract/audio"
    }


# Endpoint de verificación de salud de la API
@app.get("/health")
def health_check():
    return {"status": "healthy"}


def extract_document(file: UploadFile, lang: Optional[str] = None) -> dict:
    """Extrae el texto una sola vez con la misma lógica para las dos rutas."""
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


def synthesize_speech(text: str, tts_lang: str) -> bytes:
    """Envía el texto a Google y devuelve los bytes del MP3, sin guardarlo en disco."""
    if tts_lang not in SUPPORTED_TTS_LANGS:
        raise HTTPException(status_code=400, detail="Idioma de voz no soportado. Usa es o en.")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No se encontró texto para convertir a voz.")
    # El límite evita generar audios excesivos en una sola petición. No se trunca el texto.
    if len(text) > MAX_TTS_CHARACTERS:
        raise HTTPException(
            status_code=413,
            detail=f"El texto supera el límite de {MAX_TTS_CHARACTERS} caracteres para voz. Divide el documento.",
        )

    try:
        # gTTS divide el texto en fragmentos y escribe el MP3 completo en este búfer.
        # El idioma ya se validó arriba; lang_check=False evita consultas adicionales.
        # Los tiempos son por conexión y lectura, no un límite total del documento.
        with io.BytesIO() as audio:
            speech = gTTS(text=text, lang=tts_lang, lang_check=False, timeout=(5, 30))
            speech.write_to_fp(audio)
            audio_bytes = audio.getvalue()
        if not audio_bytes:
            raise HTTPException(status_code=503, detail="El servicio de voz devolvió un audio vacío.")
        return audio_bytes
    except gTTSError as exc:
        # No incluimos texto del documento en el registro ni detalles del proveedor al cliente.
        logger.warning("El servicio TTS no pudo completar la síntesis.")
        raise HTTPException(
            status_code=503,
            detail="No se pudo generar el audio. Revisa la conexión a Internet o inténtalo más tarde.",
        ) from exc
    except (AssertionError, ValueError) as exc:
        # Algunos textos, por ejemplo solo signos, quedan vacíos al prepararlos para voz.
        raise HTTPException(status_code=400, detail="El texto no contiene contenido que se pueda leer en voz.") from exc


@app.post("/extract", status_code=status.HTTP_200_OK)
def extract_text(
    file: UploadFile = File(...),
    lang: Optional[str] = Query(None, description="Idioma OCR: spa, eng o spa+eng"),
):
    """Devuelve el texto y los metadatos del documento en JSON."""
    # FastAPI ejecuta estas rutas síncronas en hilos para no bloquear otras peticiones.
    return extract_document(file, lang)


@app.post(
    "/extract/audio",
    response_class=Response,
    responses={
        200: {"description": "Audio MP3 del texto extraído.", "content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}},
        400: {"description": "Archivo, idioma o texto no válido."},
        413: {"description": "El texto supera el límite de síntesis."},
        503: {"description": "Motor OCR o servicio de voz no disponible."},
    },
)
def extract_audio(
    file: UploadFile = File(...),
    lang: Optional[str] = Query(None, description="Idioma OCR: spa, eng o spa+eng"),
    tts_lang: str = Query("es", description="Idioma de voz: es (español) o en (inglés). No traduce el texto."),
) -> Response:
    """Extrae el documento y envía el texto a Google para devolver su lectura en MP3."""
    # Se valida antes del OCR para no procesar un documento con una voz no admitida.
    if tts_lang not in SUPPORTED_TTS_LANGS:
        raise HTTPException(status_code=400, detail="Idioma de voz no soportado. Usa es o en.")

    document = extract_document(file, lang)
    audio = synthesize_speech(document["extracted_text"], tts_lang)

    # Se devuelve el archivo completo; el nombre fijo evita usar entradas del usuario
    # en las cabeceras HTTP. No se crea una ruta pública ni se conserva el audio.
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": 'attachment; filename="lectura.mp3"',
            "Cache-Control": "no-store",
        },
    )
