import io
import time
from typing import List
import docx
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile, status

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

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

# Endpoint de verificación de salud de la APi
@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/extract", status_code=status.HTTP_200_OK)
async def extract_text(file: UploadFile = File(...)):
    start_time = time.time()

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionó ningún archivo válido."
        )

    content_type = file.content_type
    filename = file.filename
    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo proporcionado está vacío."
        )

    extracted_pages = []
    full_text = []

    # 1. Procesamiento de IMÁGENES (Tesseract OCR)
    if content_type in ALLOWED_IMAGE_TYPES or filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        try:
            image = Image.open(io.BytesIO(contents))
            clean_text = pytesseract.image_to_string(image, lang='spa').strip()

            extracted_pages.append({"page": 1, "text": clean_text})
            if clean_text:
                full_text.append(clean_text)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar la imagen con OCR: {str(e)}"
            )

    # 2. Procesamiento de PDF (PyMuPDF + Tesseract fallback)
    elif content_type in ALLOWED_PDF_TYPES or filename.lower().endswith('.pdf'):
        try:
            pdf_document = fitz.open(stream=contents, filetype="pdf")
            
            for page_index in range(len(pdf_document)):
                page_num = page_index + 1
                page = pdf_document[page_index]

                page_text = page.get_text("text").strip()

                # Fallback a OCR si la página carece de capa de texto
                if not page_text:
                    pix = page.get_pixmap()
                    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    page_text = pytesseract.image_to_string(image, lang='spa').strip()

                extracted_pages.append({"page": page_num, "text": page_text})
                if page_text:
                    full_text.append(page_text)

            pdf_document.close()

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar el documento PDF: {str(e)}"
            )

    # 3. Procesamiento de WORD / DOCX (python-docx)
    elif content_type in ALLOWED_DOCX_TYPES or filename.lower().endswith('.docx'):
        try:
            doc = docx.Document(io.BytesIO(contents))
            paragraphs_text = []

            # Extracción de párrafos
            for p in doc.paragraphs:
                if p.text.strip():
                    paragraphs_text.append(p.text.strip())

            # Extracción de celdas en tablas
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_text:
                        paragraphs_text.append(" | ".join(row_text))

            docx_text = "\n".join(paragraphs_text)

            extracted_pages.append({"page": 1, "text": docx_text})
            if docx_text:
                full_text.append(docx_text)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar el documento Word: {str(e)}"
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado ({content_type}). Se admiten PDF, DOCX e imágenes (PNG, JPG)."
        )

    processing_time = round(time.time() - start_time, 3)

    return {
        "filename": filename,
        "content_type": content_type,
        "total_pages": len(extracted_pages),
        "extracted_text": "\n\n".join(full_text),
        "content_by_page": extracted_pages,
        "metadata": {
            "processing_time_seconds": processing_time,
            "language": "spa",
            "pages_processed": len(extracted_pages)
        }
    }