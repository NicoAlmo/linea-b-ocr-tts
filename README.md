# Línea B: microservicio de OCR y lectura accesible

API REST para extraer texto de imágenes PNG/JPEG, PDF y documentos DOCX. La entrada es `app/main.py`, con la instancia FastAPI `app`.

El alcance actual es la extracción de texto. La conversión a voz (TTS), la autenticación y el almacenamiento de documentos todavía no están implementados.

## Requisitos e instalación

- Python 3.10 o superior.
- Tesseract OCR instalado por separado; `pip` instala su interfaz Python, pero no el motor.
- Paquetes de idioma de Tesseract: `spa` para español y `eng` para inglés. La configuración predeterminada usa ambos.

Desde la carpeta del proyecto, en Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación, ejecute primero:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

Las dependencias son FastAPI, Uvicorn, python-multipart, pytesseract, Pillow, PyMuPDF y python-docx. Se requiere python-docx 1.1.2 o posterior para recorrer párrafos y tablas en su orden original.

## Configuración de OCR

El ejecutable se busca en este orden:

1. Variable de entorno `TESSERACT_CMD`.
2. Ruta habitual en Windows: `C:\Program Files\Tesseract-OCR\tesseract.exe`, si existe.
3. Comando `tesseract` disponible en `PATH`.

Configuración opcional antes de iniciar el servidor:

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
$env:OCR_LANG = 'spa'
& $env:TESSERACT_CMD --list-langs
```

`OCR_LANG` vale `spa+eng` si no se configura. Solo se admiten `spa`, `eng` y sus combinaciones. Las variables se leen al importar la aplicación: reinicie el servidor después de cambiarlas.

## Arranque

```powershell
uvicorn app.main:app --reload
```

Servicio: <http://127.0.0.1:8000>. Swagger: <http://127.0.0.1:8000/docs>.

## Endpoints

| Ruta | Método | Función |
| --- | --- | --- |
| `/` | GET | Identificación del servicio y `status: "ok"`. |
| `/health` | GET | Devuelve `{"status":"healthy"}`; comprueba la API, sin verificar Tesseract. |
| `/extract` | POST | Recibe un archivo y devuelve el texto extraído. |

### POST /extract

Cuerpo `multipart/form-data`, con el campo obligatorio `file`. El parámetro de consulta opcional `lang` sustituye `OCR_LANG` para esa petición. Use `spa`, `eng` o `spa%2Beng`; también se aceptan comas como separador.

| Formato | Extensiones | MIME admitido | Procesamiento |
| --- | --- | --- | --- |
| Imagen | `.png`, `.jpg`, `.jpeg` | `image/png`, `image/jpeg`, `image/jpg` | OCR con Tesseract. |
| PDF | `.pdf` | `application/pdf` | Lee texto nativo; si una página no contiene texto, la renderiza en RGB a 300 dpi y aplica OCR. |
| DOCX | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Lee párrafos y tablas en el orden del documento. |

La extensión reconocida decide el formato; si no existe una extensión reconocida, se usa el MIME enviado por el cliente. El contenido debe ser válido para el formato elegido. El campo de respuesta `content_type` conserva el MIME recibido, sin detectar un MIME nuevo.

Ejemplos para PowerShell, usando archivos locales reales:

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -X POST 'http://127.0.0.1:8000/extract?lang=spa' -F 'file=@imagen.png'
curl.exe -X POST 'http://127.0.0.1:8000/extract?lang=spa%2Beng' -F 'file=@documento.pdf'
curl.exe -X POST 'http://127.0.0.1:8000/extract' -F 'file=@documento.docx' -o respuesta.json
```

En Swagger, abra **POST /extract**, pulse **Try it out**, seleccione el archivo, indique el idioma si lo necesita y pulse **Execute**.

Respuesta de ejemplo para un PDF de una página:

```json
{
  "filename": "documento.pdf",
  "content_type": "application/pdf",
  "total_pages": 1,
  "extracted_text": "Texto del documento",
  "content_by_page": [
    {"page": 1, "text": "Texto del documento"}
  ],
  "metadata": {
    "processing_time_seconds": 0.125,
    "language": "spa+eng",
    "pages_processed": 1
  }
}
```

- `total_pages` y `pages_processed`: páginas recorridas. Las imágenes y los DOCX se representan como un único bloque con `page: 1`; no es la paginación visual de Word.
- `extracted_text`: texto de páginas no vacías, separado por dos saltos de línea.
- `content_by_page`: incluye también páginas sin texto, con numeración desde 1.
- `processing_time_seconds`: duración de la extracción, sin incluir la transferencia del archivo.
- `language`: idioma seleccionado para OCR, incluso si el documento se resuelve mediante texto nativo.

Una extracción sin texto puede devolver HTTP 200 con cadenas vacías.

### Errores

| Código | Causa |
| --- | --- |
| 400 | Archivo vacío, nombre inválido, formato o idioma no admitido, errores de contenido detectados o PDF protegido con contraseña. |
| 422 | Falta el campo obligatorio `file` o la petición no cumple la validación de FastAPI. |
| 503 | Tesseract no está disponible, falta un idioma solicitado o falla el motor OCR. El tiempo máximo por llamada de OCR es 120 segundos. |
| 500 | Error inesperado del procesamiento. El detalle técnico se registra en el servidor. |

Los errores incluyen `detail`. Los PDF con texto nativo y los DOCX no necesitan Tesseract; la comprobación del motor ocurre cuando se necesita OCR.

## Organización del código

```text
app/
  __init__.py       # Paquete Python.
  main.py           # Configuración, rutas y extracción por formato.
requirements.txt    # Dependencias Python.
README.md           # Instalación, uso y limitaciones.
AGENTS.md           # Instrucciones de trabajo del repositorio.
```

En `main.py`, `configure_tesseract` selecciona el ejecutable, `normalize_lang` valida el idioma y `run_ocr` comprueba idiomas y ejecuta Tesseract. `extract_text` valida el archivo, selecciona el procesamiento y construye una respuesta común. FastAPI ejecuta esta ruta síncrona en un hilo para que el trabajo de OCR no bloquee el bucle de eventos. Los contextos de imágenes y PDF cierran los recursos incluso si ocurre un error.

## Verificación y limitaciones actuales

No hay suite de pruebas, CI, linter ni typecheck configurados. Para verificar manualmente, inicie el servidor, consulte `/health` y envíe archivos reales desde Swagger o los comandos anteriores. Compruebe un PNG/JPEG, un PDF con texto, un PDF escaneado y un DOCX con párrafos y tablas; pruebe también archivos vacíos y dañados.

- La calidad del OCR depende de la resolución, orientación y legibilidad de la imagen.
- El fallback de PDF solo se activa en páginas sin texto extraíble; no recupera imágenes con texto dentro de páginas que ya tienen una capa textual.
- DOCX extrae párrafos y tablas del cuerpo; no procesa imágenes incrustadas mediante OCR ni incluye encabezados, pies o cuadros de texto. Las tablas se convierten en filas separadas por saltos de línea y celdas separadas por ` | `.
- El archivo se lee completo en memoria. No hay límite de tamaño de carga ni de páginas configurado en la aplicación. El límite de 120 segundos es por llamada OCR, no por documento.
- `/health` puede responder correctamente aunque Tesseract no esté instalado.

Desarrollado como parte de la tesis de licenciatura **Línea B - Microservicio de OCR y Lectura Accesible**.
