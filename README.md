# Línea B: Microservicio de OCR y Lectura Accesible

Microservicio REST encargado de la extracción de texto impreso desde archivos de imagen, PDF y DOCX mediante técnicas de Reconocimiento Óptico de Caracteres (OCR) y procesamiento de documentos nativos. Este componente forma parte de la arquitectura de remediación de accesibilidad educativa, proporcionando la capa de ingestión y extracción textual para su posterior conversión a audio sintético (TTS) en apoyo a estudiantes con discapacidad visual.

**Stack técnico:** Python 3.10+, FastAPI, Uvicorn, Tesseract OCR (vía `pytesseract`), PyMuPDF (`fitz`), `python-docx`.

---

## Requisitos Previos

- Python 3.10 o superior.
- Tesseract OCR instalado en el sistema operativo con soporte para el idioma español (`spa`). En Windows, el ejecutable se espera en `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- Git para Windows.
- PowerShell.

---

## Instrucciones de Ejecución Local

### 1. Clonar el repositorio

```powershell
git clone https://github.com/NicoAlmo/linea-b-ocr-tts.git
cd linea-b-ocr-tts
```

### 2. Crear y activar el entorno virtual

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación del script, establezca temporalmente la política de ejecución:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

### 3. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 4. Iniciar el servidor local

```powershell
uvicorn app.main:app --reload
```

El servicio quedará disponible en `http://127.0.0.1:8000`.

---

## Tabla de Endpoints Disponibles

| Ruta                            | Método HTTP | Descripción                                | Respuesta Esperada                                                 |
| ------------------------------- | ----------- | ------------------------------------------ | ------------------------------------------------------------------ |
| `http://127.0.0.1:8000/`        | GET         | Endpoint raíz de comprobación del servicio | JSON con `status: "ok"`, nombre del servicio y mensaje informativo |
| `http://127.0.0.1:8000/health`  | GET         | Health check para orquestación y monitoreo | `{"status": "healthy"}`                                            |
| `http://127.0.0.1:8000/docs`    | GET         | Documentación interactiva Swagger UI       | Interfaz gráfica para prueba de endpoints                          |
| `http://127.0.0.1:8000/extract` | POST        | Extracción de texto desde archivo subido   | JSON con texto extraído, metadatos y contenido por página          |

---

## Documentación del Endpoint POST /extract

### Estrategia de procesamiento por formato

| Formato  | Extensiones             | MIME Types                                                                | Motor de extracción                                                                                                              |
| -------- | ----------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Imágenes | `.png`, `.jpg`, `.jpeg` | `image/png`, `image/jpeg`, `image/jpg`                                    | OCR directo con Tesseract (`pytesseract`), idioma `spa`                                                                          |
| PDF      | `.pdf`                  | `application/pdf`                                                         | Lectura de capa vectorial con PyMuPDF (`fitz`); _fallback_ a Tesseract OCR si la página es escaneada y carece de texto extraíble |
| Word     | `.docx`                 | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Extracción de párrafos y tablas mediante `python-docx`                                                                           |

### Parámetro de entrada

- **Content-Type:** `multipart/form-data`
- **Campo:** `file` (requerido): Archivo binario a procesar.

### Respuesta exitosa (HTTP 200 OK)

```json
{
  "filename": "documento.pdf",
  "content_type": "application/pdf",
  "total_pages": 3,
  "extracted_text": "Texto completo de la página 1...\n\nTexto completo de la página 2...\n\nTexto completo de la página 3...",
  "content_by_page": [
    { "page": 1, "text": "Texto completo de la página 1..." },
    { "page": 2, "text": "Texto completo de la página 2..." },
    { "page": 3, "text": "Texto completo de la página 3..." }
  ],
  "metadata": {
    "processing_time_seconds": 1.234,
    "language": "spa",
    "pages_processed": 3
  }
}
```

Campos de la respuesta:

- `filename`: Nombre original del archivo subido.
- `content_type`: MIME type detectado del archivo.
- `total_pages`: Número total de páginas procesadas (1 para imágenes y DOCX).
- `extracted_text`: Concatenación de todo el texto extraído, separado por doble salto de línea entre páginas.
- `content_by_page`: Lista de objetos con `page` (número de página, iniciando en 1) y `text` (contenido de esa página).
- `metadata`: Objeto con `processing_time_seconds` (tiempo total de procesamiento en segundos), `language` (idioma de OCR utilizado) y `pages_processed` (cantidad de páginas procesadas).

### Códigos de error comunes

| Código HTTP               | Causa                                                                                                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 400 Bad Request           | No se proporcionó archivo (`file` ausente), archivo vacío, o formato MIME/extensión no soportada.                                                                        |
| 500 Internal Server Error | Fallo interno durante el procesamiento: error de Tesseract, PyMuPDF, python-docx, o archivo corrupto. El cuerpo de la respuesta incluye `detail` con la traza del error. |

---

## Opciones de Prueba del Endpoint

### Opción 1: Swagger UI

1. Inicie el servicio: `uvicorn app.main:app --reload`
2. Abra el navegador en `http://127.0.0.1:8000/docs`
3. Localice la operación **POST /extract**
4. Haga clic en **Try it out**
5. En el campo `file`, seleccione un archivo local (imagen, PDF o DOCX)
6. Presione **Execute** y observe la respuesta JSON

---

### Opción 2: cURL

**PDF:**

```bash
curl -X POST "http://127.0.0.1:8000/extract" \
  -F "file=@documento.pdf"
```

**Imagen (PNG/JPG):**

```bash
curl -X POST "http://127.0.0.1:8000/extract" \
  -F "file=@imagen.png"
```

**Documento Word (DOCX):**

```bash
curl -X POST "http://127.0.0.1:8000/extract" \
  -F "file=@documento.docx"
```

Para guardar la respuesta en un archivo: `curl -X POST "http://127.0.0.1:8000/extract" -F "file=@archivo.pdf" -o respuesta.json`

---

### Opción 3: Script de Python

```python
import requests
import mimetypes
import sys
from pathlib import Path

def test_extract(filepath):
    """
    Envía un archivo al endpoint /extract y muestra el resultado en consola.
    """
    url = "http://127.0.0.1:8000/extract"
    path = Path(filepath)

    if not path.is_file():
        print("[ERROR] Archivo no encontrado: {}".format(filepath), file=sys.stderr)
        sys.exit(1)

    # Detección de MIME type por extensión
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type is None:
        mime_type = "application/octet-stream"

    print("[INFO] Enviando {} ({})...".format(path.name, mime_type))

    with open(path, "rb") as f:
        files = {"file": (path.name, f, mime_type)}
        response = requests.post(url, files=files)

    if response.status_code == 200:
        data = response.json()
        print("\n--- RESPUESTA EXITOSA ---")
        print("Archivo:         {}".format(data["filename"]))
        print("Tipo MIME:       {}".format(data["content_type"]))
        print("Páginas:         {}".format(data["total_pages"]))
        print("Tiempo proceso:  {} s".format(data["metadata"]["processing_time_seconds"]))
        print("Idioma OCR:      {}".format(data["metadata"]["language"]))
        print("Longitud texto:  {} caracteres".format(len(data["extracted_text"])))
        print("\n--- TEXTO EXTRAÍDO (primeros 500 caracteres) ---")
        texto = data["extracted_text"]
        print(texto[:500] + ("..." if len(texto) > 500 else ""))
    else:
        print("\n[ERROR] HTTP {}".format(response.status_code))
        try:
            print(response.json())
        except ValueError:
            print(response.text)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python test_extract.py <ruta_al_archivo>")
        sys.exit(1)
    test_extract(sys.argv[1])
```

**Uso:**

```powershell
python test_extract.py .\documento.pdf
python test_extract.py .\imagen.png
python test_extract.py .\documento.docx
```

---

## Licencia y Autoría

Desarrollado como parte de la tesis de licenciatura **Línea B - Microservicio de OCR y Lectura Accesible**.

Repositorio: `https://github.com/NicoAlmo/linea-b-ocr-tts.git`
