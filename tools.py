# tools.py
import os
import json
import re
import requests
from openai import OpenAI
from dotenv import load_dotenv
from memory import ConversationMemory

# Cargar variables de entorno
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ Falta OPENAI_API_KEY en .env")

client = OpenAI(api_key=api_key)
memory = ConversationMemory("conversation.json")  # memoria persistente

# ---------- Función de clima ----------
def get_weather(latitude, longitude):
    """
    Obtiene la temperatura actual y condiciones usando la API de Open-Meteo,
    y devuelve una frase en lenguaje natural.
    """
    try:
        response = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&current=temperature_2m,wind_speed_10m,weathercode"
        )
        data = response.json()
        temp = data["current"]["temperature_2m"]
        wind = data["current"]["wind_speed_10m"]

        return f"La temperatura actual es de {temp}°C con un viento de {wind} km/h."
    except Exception as e:
        return f"Error al obtener el clima: {e}"


def call_function(name, args):
    """Ejecuta la función llamada por el modelo."""
    if name == "get_weather":
        return get_weather(**args)
    raise ValueError(f"Función desconocida: {name}")


# ---------- Auxiliar: extraer lugar ----------
def extract_location(user_text: str) -> str:
    """
    Extrae un posible lugar del texto del usuario.
    Ejemplo: 'Clima en Albacete' -> 'Albacete'
    """
    match = re.search(r"(?:en|de)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", user_text)
    if match:
        return match.group(1).strip()
    return ""


# ---------- Inteligencia con herramientas ----------
def intelligence_with_tools(prompt: str) -> str:
    tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Obtiene temperatura actual y condiciones en ºC y km/h para unas coordenadas",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]

    try:
        # 1️⃣ Guardar mensaje del usuario
        memory.add_message("user", prompt)

        # 2️⃣ Tomar solo las últimas 5 interacciones
        last_msgs = memory.get_last_messages(5)

        # 3️⃣ Crear mensaje system con resumen
        summary_text = "\n".join(f"{m['role']}: {m['content']}" for m in last_msgs)
        input_messages = [{"role": "system", "content": f"Resumen de últimas interacciones:\n{summary_text}"}]

        # 4️⃣ Agregar prompt actual
        input_messages.append({"role": "user", "content": prompt})

        # 5️⃣ Llamada al modelo
        response = client.responses.create(
            model="gpt-4o",
            input=input_messages,
            tools=tools,
        )

        final_text = ""
        # 6️⃣ Procesar outputs
        for output in response.output:
            if output.type == "message":
                content = output.content[0].text
                memory.add_message("assistant", content)
                final_text += content

            elif output.type == "function_call":
                name = output.name
                args = json.loads(output.arguments)
                result = call_function(name, args)
                memory.add_message("assistant", result)
                final_text += result

        # 7️⃣ Incluir ciudad si aplica
        location = extract_location(prompt)
        if location and "La temperatura actual" in final_text:
            final_text = final_text.replace(
                "La temperatura actual",
                f"En {location} la temperatura actual"
            )

        # 8️⃣ Fallback si no hay respuesta
        if not final_text.strip():
            final_text = "Perdona, parece que hubo un error al generar la respuesta."
            memory.add_message("assistant", final_text)

        return final_text

    except Exception as e:
        error_msg = f"Hubo un error procesando tu solicitud: {e}"
        memory.add_message("assistant", error_msg)
        return error_msg
