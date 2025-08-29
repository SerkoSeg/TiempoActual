import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Importa tu lógica desde tools.py
from tools import intelligence_with_tools

# Importa utilidades de Gmail
from gmail.gmail_utils import (
    get_service,
    get_or_create_label,
    list_unread_to_me,
    get_message,
    extract_text_from_message,
    get_sender_email,
    send_email,
    mark_as_processed,
    SUBJECT,
    LABEL_NAME,
)

# Inicializar FastAPI
app = FastAPI()

# Configurar carpetas de estáticos y plantillas
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --------- FUNCIONES AUXILIARES ----------
def get_subject(msg):
    """Extrae el asunto de un mensaje de Gmail"""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == "subject":
            return h["value"]
    return ""

# --------- RUTAS ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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

@app.get("/process_emails")
async def process_emails():
    service = get_service()
    label_id = get_or_create_label(service, LABEL_NAME)
    messages = list_unread_to_me(service, max_results=10)

    processed = []
    for m in messages:
        msg = get_message(service, m["id"])
        sender = get_sender_email(msg)
        body_in = extract_text_from_message(msg)
        subject_in = get_subject(msg)

        if not sender:
            mark_as_processed(service, m["id"], label_id)
            continue

        # Combinar asunto y cuerpo en un solo texto para la IA
        combined_text = f"Asunto: {subject_in}\nMensaje: {body_in}".strip()

        try:
            reply = intelligence_with_tools(combined_text)
            send_email(service, sender, SUBJECT, reply)
            processed.append(sender)
        finally:
            mark_as_processed(service, m["id"], label_id)

    return {"processed": processed, "count": len(processed)}

# Servidor para Render (usa el puerto que da Render)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
