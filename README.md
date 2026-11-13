# Línea B: microservicio de OCR y lectura accesible

API REST para extraer texto de imágenes PNG/JPEG, PDF y documentos DOCX. La entrada es `app/main.py`, con la instancia FastAPI `app`.

El alcance actual incluye extracción de texto y síntesis de voz (TTS) en MP3. La autenticación y el almacenamiento de documentos o audios todavía no están implementados.

La voz se genera con `gTTS`, que utiliza el servicio de Google Translate: requiere Internet y envía el texto extraído a Google. El OCR y la extracción nativa siguen funcionando localmente. No se necesita una clave API para esta integración; su disponibilidad depende del proveedor externo.

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

Las dependencias son FastAPI, Uvicorn, python-multipart, pytesseract, Pillow, PyMuPDF, python-docx, gTTS y langdetect. Se requiere python-docx 1.1.2 o posterior para recorrer párrafos y tablas en su orden original. Si ya tenías instalado el proyecto, vuelve a ejecutar `python -m pip install -r requirements.txt` para instalar las dependencias de voz y detección de idioma.

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
| `/extract/audio` | POST | Recibe un archivo y devuelve directamente el MP3 con su lectura. Requiere Internet. |

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

### POST /extract/audio: del documento a la voz

TTS significa *Text-to-Speech*: convierte un texto escrito en una lectura de voz. Esta ruta realiza dos pasos: extrae el texto con la misma lógica de `/extract` y lo envía a gTTS para obtener un MP3.

| Parámetro | Ubicación | Obligatorio | Uso |
| --- | --- | --- | --- |
| `file` | Cuerpo multipart | Sí | PNG, JPEG, PDF o DOCX. |
| `lang` | Consulta | No | Idioma del OCR: `spa`, `eng` o `spa+eng`. Usa `OCR_LANG` o `spa+eng` si se omite. |
| `tts_lang` | Consulta | No | `auto` (predeterminado: detectar español o inglés), `es` (forzar español) o `en` (forzar inglés). |

`lang` ayuda a reconocer las letras de una imagen; `tts_lang` determina la pronunciación de la lectura. Con `auto`, la aplicación analiza localmente el texto extraído con `langdetect` y selecciona una voz en español o inglés. No traduce: lee el texto en el idioma identificado. Un PDF con texto seleccionable no necesita OCR, pero sí necesita Internet para generar su audio. La detección no cambia la configuración del OCR.

Si omites `tts_lang`, también se aplica la detección automática. Si envías explícitamente `es` o `en`, se respeta tu elección aunque no coincida con el texto. La respuesta MP3 incluye la cabecera `Content-Language: es` o `Content-Language: en` para indicar la voz utilizada.

La detección es una estimación y puede equivocarse con textos cortos, nombres, errores de OCR o documentos que mezclen idiomas. Se acepta el resultado si el idioma más probable es español o inglés y su puntuación alcanza 0.80; esa puntuación no garantiza exactitud. Si no hay suficiente claridad, se devuelve HTTP 400 y se pide elegir `es` o `en` manualmente. Se usa una sola voz para todo el documento, sin cambiar de idioma por párrafo.

Ejemplos para PowerShell:

```powershell
# Detectar el idioma y descargar la lectura sin elegir una voz manualmente.
curl.exe --fail-with-body -X POST 'http://127.0.0.1:8000/extract/audio' -F 'file=@documento.pdf' -o lectura.mp3

# Documento en español: guarda la respuesta MP3 en tu computadora.
curl.exe --fail-with-body -X POST 'http://127.0.0.1:8000/extract/audio?lang=spa&tts_lang=es' -F 'file=@documento.pdf' -o lectura.mp3

# Documento en inglés.
curl.exe --fail-with-body -X POST 'http://127.0.0.1:8000/extract/audio?lang=eng&tts_lang=en' -F 'file=@documento.docx' -o reading.mp3
```

En Swagger abre **POST /extract/audio**, pulsa **Try it out**, deja `tts_lang` en `auto` (o selecciona una voz manualmente), carga el archivo y pulsa **Execute**. Una respuesta exitosa permite descargar el audio. El servidor devuelve HTTP 200 con `Content-Type: audio/mpeg` y `Content-Disposition: attachment; filename="lectura.mp3"`. La respuesta contiene bytes de audio, no JSON ni una ruta. Si hay un error, devuelve JSON con `detail`; comprueba el estado HTTP antes de reproducir la descarga.

El MP3 se construye completo en memoria y se envía al cliente. La aplicación no lo guarda en disco ni ofrece una URL para recuperarlo después. `-o lectura.mp3` guarda el archivo en la computadora desde la que ejecutas cURL. Para recibir texto y audio por separado puedes usar `/extract` y `/extract/audio`; cada petición vuelve a procesar el documento.

Errores adicionales de esta ruta:

| Código | Causa |
| --- | --- |
| 400 | Idioma de voz distinto de `auto`/`es`/`en`, texto vacío o sin contenido pronunciable, o detección automática sin un resultado claro en español o inglés. |
| 413 | Texto extraído de más de 20 000 caracteres. Se rechaza completo; no se recorta ni se omiten páginas. Divide el documento. |
| 503 | El proveedor de voz no responde o no se pudo completar la síntesis. Revisa Internet y vuelve a intentarlo. |

También pueden ocurrir los errores de extracción descritos en la sección anterior. Los tiempos de espera de TTS son 5 segundos para conexión y 30 para lectura por solicitud al proveedor; gTTS puede dividir el texto en varias solicitudes. No es un límite total de duración del documento.

Referencia del motor: [documentación de gTTS](https://gtts.readthedocs.io/en/latest/module.html).
Referencia de detección: [documentación de langdetect](https://github.com/Mimino666/langdetect).

## Organización del código

```text
app/
  __init__.py       # Paquete Python.
  main.py           # Configuración, rutas, extracción y síntesis de voz.
requirements.txt    # Dependencias Python.
README.md           # Instalación, uso y limitaciones.
AGENTS.md           # Instrucciones de trabajo del repositorio.
```

En `main.py`:

- `configure_tesseract` selecciona el ejecutable de OCR.
- `normalize_lang` valida el idioma del OCR y `run_ocr` comprueba idiomas y ejecuta Tesseract.
- `extract_document` valida el archivo, selecciona el procesamiento y construye el resultado común para ambas rutas.
- `extract_text` devuelve ese resultado en JSON desde `/extract`.
- `validate_speech_text` comprueba que haya texto y que no supere el límite de síntesis.
- `resolve_tts_language` conserva la voz manual o detecta español/inglés en modo `auto`.
- `synthesize_speech` valida el idioma y la longitud del texto, llama a gTTS y devuelve los bytes MP3.
- `extract_audio` conecta la extracción con la síntesis y construye la respuesta descargable de `/extract/audio`.

FastAPI ejecuta las rutas síncronas en hilos para que el OCR y la espera del servicio de voz no bloqueen el bucle de eventos. Los contextos de imágenes, PDF y búfer de audio cierran los recursos incluso si ocurre un error.

## Verificación y limitaciones actuales

No hay suite de pruebas, CI, linter ni typecheck configurados. Para verificar manualmente, inicie el servidor, consulte `/health` y envíe archivos reales desde Swagger o los comandos anteriores. Compruebe un PNG/JPEG, un PDF con texto, un PDF escaneado y un DOCX con párrafos y tablas; pruebe también archivos vacíos y dañados.

- La calidad del OCR depende de la resolución, orientación y legibilidad de la imagen.
- El fallback de PDF solo se activa en páginas sin texto extraíble; no recupera imágenes con texto dentro de páginas que ya tienen una capa textual.
- DOCX extrae párrafos y tablas del cuerpo; no procesa imágenes incrustadas mediante OCR ni incluye encabezados, pies o cuadros de texto. Las tablas se convierten en filas separadas por saltos de línea y celdas separadas por ` | `.
- El archivo se lee completo en memoria. No hay límite de tamaño de carga ni de páginas configurado en la aplicación. El límite de 120 segundos es por llamada OCR, no por documento.
- `/health` puede responder correctamente aunque Tesseract no esté instalado.
- Para comprobar TTS, envía un documento a `/extract/audio`, descarga y reproduce el MP3. Comprueba español e inglés con `auto` y selección manual, textos ambiguos, documentos sin texto, el límite de caracteres y la respuesta cuando no hay conexión.
- La síntesis depende de un servicio externo; no funciona sin Internet. El texto se transmite a Google. La aplicación no conserva el audio, pero eso no implica que el procesamiento del proveedor sea local.

Desarrollado como parte de la tesis de licenciatura **Línea B - Microservicio de OCR y Lectura Accesible**.
