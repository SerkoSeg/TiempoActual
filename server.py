import os
import sqlite3
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
    get_message_id,
    SUBJECT,
    LABEL_NAME,
)

# Inicializar FastAPI
app = FastAPI()

# Configurar carpetas de estáticos y plantillas
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --------- BASE DE DATOS PARA RESÚMENES ----------
DB_PATH = BASE_DIR / "conversations.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summary (
            sender TEXT PRIMARY KEY,
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_summary(sender):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT summary FROM conversation_summary WHERE sender=?", (sender,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def save_summary(sender, summary):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO conversation_summary (sender, summary)
        VALUES (?, ?)
        ON CONFLICT(sender) DO UPDATE SET summary=excluded.summary
    """, (sender, summary))
    conn.commit()
    conn.close()

# Crear DB si no existe
init_db()

# --------- FUNCIONES AUXILIARES ----------
def get_subject(msg):
    """Extrae el asunto de un mensaje de Gmail"""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == "subject":
            return h["value"]
    return ""

# --------- RUTAS ----------
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.api_route("/process_emails", methods=["GET", "HEAD"])
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
        thread_id = msg.get("threadId")
        message_id = get_message_id(msg)

        if not sender:
            mark_as_processed(service, m["id"], label_id)
            continue

        # Recuperar el resumen actual del remitente
        prev_summary = get_summary(sender)

        # Crear prompt para actualizar resumen
        prompt = f"""
        Resumen previo de la conversación:
        {prev_summary}

        Nuevo mensaje del usuario:
        {body_in}

        Actualiza el resumen de la conversación manteniéndolo conciso:
        """

        try:
            # Generar nuevo resumen usando IA
            new_summary = intelligence_with_tools(prompt)

            # Guardar resumen actualizado
            save_summary(sender, new_summary)

            # Preparar respuesta al usuario usando el resumen
            context_for_reply = f"Resumen de la conversación hasta ahora: {new_summary}\n\nUsuario dice: {body_in}"
            reply = intelligence_with_tools(context_for_reply)

            # Enviar respuesta en el mismo hilo
            send_email(service, sender, SUBJECT, reply, thread_id=thread_id, in_reply_to=message_id)

            processed.append(sender)
        finally:
            mark_as_processed(service, m["id"], label_id)

    return {"processed": processed, "count": len(processed)}

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
