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


def _get_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


HOST = _get_str("HOST", "127.0.0.1")
PORT = _get_int("PORT", 8000)
MT4_API_KEY = _get_str("MT4_API_KEY", "")
MT4_API_KEYS = _get_list("MT4_API_KEYS")
MT4_ALLOWED_API_KEYS = tuple(dict.fromkeys([*MT4_API_KEYS, *([MT4_API_KEY] if MT4_API_KEY else [])]))
CORS_ORIGINS = tuple(_get_list("CORS_ORIGINS"))
ALLOWED_HOSTS = tuple(_get_list("ALLOWED_HOSTS"))

# Bloqueo operativo alrededor de noticias.
BLOCK_HIGH_IMPACT_MINUTES = _get_int("BLOCK_HIGH_IMPACT_MINUTES", 30)
BLOCK_MEDIUM_IMPACT_MINUTES = _get_int("BLOCK_MEDIUM_IMPACT_MINUTES", 15)

# Escalado conservador para convertir net positions COT a un sesgo [-1, +1].
COT_BIAS_DIVISOR = _get_int("COT_BIAS_DIVISOR", 150000)
