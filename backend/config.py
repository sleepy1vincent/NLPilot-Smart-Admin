import os
from dotenv import load_dotenv

load_dotenv()
class Config:
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "nlpilot")

    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    PORT = int(os.getenv("FLASK_PORT", 5001))
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    # 多步循环开关：默认关，稳定后再打开
    CHAT_LOOP = os.getenv("CHAT_LOOP", "0") == "1"
    CHAT_MAX_STEPS = int(os.getenv("CHAT_MAX_STEPS", 3))