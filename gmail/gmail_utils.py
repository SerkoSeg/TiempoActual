# gmail_utils.py
import os
import base64
import json
import re
import time
from email.mime.text import MIMEText
from email.utils import parseaddr

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Scopes mínimos para leer y responder correos
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

LABEL_NAME = "AutoRespondido"
TARGET_TO = "tiempoactualizado@gmail.com"
SUBJECT = "Tiempo Actual"

# --------- CARGA DE CREDENCIALES ----------
def load_creds():
    # Busca token.json dentro de la carpeta gmail
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if os.path.exists(token_path):
        # Local: archivo generado con auth_local.py
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    else:
        token_json_env = os.getenv("GMAIL_TOKEN_JSON")
        if token_json_env:
            data = json.loads(token_json_env)
            creds = Credentials.from_authorized_user_info(data, SCOPES)
        else:
            raise RuntimeError("❌ No se encontró ni gmail/token.json ni GMAIL_TOKEN_JSON")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("❌ Credenciales inválidas, regenera token.json")
    return creds


def get_service():
    creds = load_creds()
    return build("gmail", "v1", credentials=creds)

# --------- LABELS ----------
def get_or_create_label(service, name):
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        if lb["name"] == name:
            return lb["id"]
    body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    created = service.users().labels().create(userId="me", body=body).execute()
    return created["id"]

# --------- LECTURA MENSAJES ----------
def list_unread_to_me(service, max_results=10):
    query = f"is:unread to:{TARGET_TO}"
    res = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return res.get("messages", [])

def get_message(service, msg_id):
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

def _find_part(parts, mime):
    for p in parts:
        if p.get("mimeType") == mime and "body" in p and "data" in p["body"]:
            return p["body"]["data"]
        if p.get("parts"):
            x = _find_part(p["parts"], mime)
            if x:
                return x
    return None

def extract_text_from_message(msg):
    payload = msg.get("payload", {})
    data = None

    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        data = payload["body"]["data"]
    elif payload.get("parts"):
        data = _find_part(payload["parts"], "text/plain")

    if not data and payload.get("parts"):
        data = _find_part(payload["parts"], "text/html")

    if data:
        text = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    return msg.get("snippet", "").strip()

def get_sender_email(msg):
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == "from":
            return parseaddr(h["value"])[1]
    return None

def get_message_id(msg):
    """Extrae el Message-ID de un correo de Gmail"""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == "message-id":
            return h["value"]
    return None

# --------- ENVÍO ----------
def send_email(service, to, subject, body_text, thread_id=None, in_reply_to=None):
    message = MIMEText(body_text)
    message["to"] = to
    message["subject"] = subject

    # Si queremos que la respuesta se inserte en el mismo hilo
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw}

    if thread_id:
        body["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=body).execute()

def mark_as_processed(service, msg_id, label_id):
    body = {"removeLabelIds": ["UNREAD"], "addLabelIds": [label_id]}
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()
