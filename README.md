# Línea B: Microservicio de OCR y Lectura Accesible

Microservicio encargado de recibir documentos o imágenes con texto impreso, extraer su contenido mediante OCR (Reconocimiento Óptico de Caracteres) y convertirlo en audio sintético (TTS) para apoyar la lectura accesible en entornos educativos.

# Puesta a punto (Sprint 0)

### Requisitos previos

- Python 3.10+
- Git para Windows
- PowerShell

### Instrucciones de Ejecución Local

### 1. Clonar el repositorio:

Abre PowerShell y clona el repositorio ejecutable:

```powershell
git clone [https://github.com/NicoAlmo/linea-b-ocr-tts.git](https://github.com/NicoAlmo/linea-b-ocr-tts.git)
cd linea-b-ocr-tts
```

### 2. Crear y activar el entorno Virtual

Crea un entorno aislado de Python para gestionar las dependencias

python -m venv venv
.\venv\Scripts\Activate.ps1

### 3. Instalar dependencias

Con el entorno virtual activo, instala los paquetes requeridos desde el archivo
requerimients.txt

pip install -r requirements.txt

### 4. Levantar el servicio

Ejecutar el servidor de desarrollo mediante Uvicorn

uvicorn app.main:app --reload

### Comprobación y Rutas Disponibles

## Ruta:

http://127.0.0.1:8000/

## Metodo:

GET

## Descripción:

Endpoint principal de comprobación

## Respuesta esperada:

Mensaje JSON con estado ok y datos del servicio

## Ruta:

http://127.0.0.1:8000/health

## Metodo:

GET

## Descripción:

Chequeo de salud del servicio (Health check)

## Respuesta esperada:

{"status": "healthy"}

## Ruta:

http://127.0.0.1:8000/docs

## Metodo:

GET

## Descripción:

Documentación interactiva e interfaz de prueba

## Respuesta esperada:

Interfaz Swagger UI para probar los endpoints en vivo.
