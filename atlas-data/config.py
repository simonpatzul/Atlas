import os

from dotenv import load_dotenv

load_dotenv()


def _get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


HOST = _get_str("HOST", "127.0.0.1")
PORT = _get_int("PORT", 8000)
MT4_API_KEY = _get_str("MT4_API_KEY", "")

# Bloqueo operativo alrededor de noticias.
BLOCK_HIGH_IMPACT_MINUTES = _get_int("BLOCK_HIGH_IMPACT_MINUTES", 30)
BLOCK_MEDIUM_IMPACT_MINUTES = _get_int("BLOCK_MEDIUM_IMPACT_MINUTES", 15)

# Escalado conservador para convertir net positions COT a un sesgo [-1, +1].
COT_BIAS_DIVISOR = _get_int("COT_BIAS_DIVISOR", 150000)
