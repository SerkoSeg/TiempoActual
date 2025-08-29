# server.py
import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Importa tu lógica desde tools.py
from tools import intelligence_with_tools  # <-- Ajusta si tu archivo se llama distinto

# Inicializar FastAPI
app = FastAPI()

# Configurar carpetas de estáticos y plantillas
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Ruta principal: muestra el chat
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Ruta POST para procesar mensajes del chat
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return JSONResponse({"reply": "Por favor escribe algo."})

    try:
        reply = intelligence_with_tools(user_message)
    except Exception as e:
        reply = f"Hubo un error procesando tu solicitud: {e}"

    return JSONResponse({"reply": reply})

# Servidor para Render (usa el puerto que da Render)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
