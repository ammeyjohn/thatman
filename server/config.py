import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 8080))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'http://localhost:7778/v1')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'Qwen3.6-35B-A3B-UD-Q4_K_XL')
