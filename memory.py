# memory.py
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ Falta OPENAI_API_KEY en .env")

client = OpenAI(api_key=api_key)


class ConversationMemory:
    def __init__(self, file_path="conversation.json"):
        self.file_path = file_path
        self.data = {"summary": "", "messages": []}
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    if "messages" not in self.data:
                        self.data["messages"] = []
                    if "summary" not in self.data:
                        self.data["summary"] = ""
            except Exception:
                self.data = {"summary": "", "messages": []}

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_message(self, role, content):
        """Añade un mensaje asegurando formato correcto."""
        if not isinstance(content, str):
            content = str(content)
        self.data["messages"].append({"role": role, "content": content})
        if len(self.data["messages"]) > 12:
            self.summarize()
        self.save()

    def get_last_messages(self, n=5):
        return self.data["messages"][-n:]

    def get_summary(self):
        return self.data["summary"]

    def summarize(self):
        """Genera resumen de la conversación para ahorrar tokens."""
        try:
            conversation_text = "\n".join(
                [f"{m['role']}: {m['content']}" 
                 for m in self.data["messages"] 
                 if isinstance(m, dict) and "role" in m and "content" in m]
            )

            prompt = (
                "Resume la siguiente conversación manteniendo los puntos clave "
                "para continuar la charla de forma coherente:\n\n" + conversation_text
            )

            response = client.responses.create(
                model="gpt-4o-mini",
                input=[{"role": "user", "content": prompt}]
            )

            summary_text = response.output_text.strip()
            if summary_text:
                self.data["summary"] = summary_text
                # Mantener solo últimas 4 interacciones
                self.data["messages"] = self.data["messages"][-5:]
                self.save()

        except Exception as e:
            print(f"⚠ Error al resumir: {e}")
