from fastapi import FastAPI

# Inicialización de la API con FastAPI
app = FastAPI(
    title="Microservicio de OCR y Lectura Accesible - Línea B",
    description="API REST para extracción de texto (OCR) y síntesis de voz (TTS).",
    version="0.1.0"
)

# Endpoint principal de prueba
@app.get("/")
def read_root():
    return {
        "status": "ok",
        "servicio": "Línea B - OCR y Lectura Accesible",
        "mensaje": "Endpoint mínimo funcional de puesta a punto (Sprint 0)"
    }

# Endpoint de verificación de salud de la API
@app.get("/health")
def health_check():
    return {"status": "healthy"}