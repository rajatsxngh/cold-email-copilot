# src/config.py
"""Settings and API clients.

Keys are read from a `.env` file in the project root. Clients are created the
first time they are needed, so the app can start even when an optional key is
missing. Only OPENAI_API_KEY is required.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# OpenAI (required)
OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4.1-mini")

# Pinecone (optional: without it, resume search runs in memory)
PINECONE_API_KEY = _env("PINECONE_API_KEY")
PINECONE_INDEX_NAME = _env("PINECONE_INDEX_NAME", "cold-email-copilot")
PINECONE_CLOUD = _env("PINECONE_CLOUD", "aws")
PINECONE_REGION = _env("PINECONE_REGION", "us-east-1")

# Hunter.io (optional: without it, you type the recruiter's email yourself)
HUNTER_API_KEY = _env("HUNTER_API_KEY")

# n8n (optional: without it, use the "Open in Gmail" button instead)
N8N_WEBHOOK_URL = _env("N8N_WEBHOOK_URL")

# all-MiniLM-L6-v2 produces 384-number embeddings
EMBEDDING_DIMENSION = 384


class MissingKeyError(RuntimeError):
    """Raised when a required API key is not set."""


@lru_cache(maxsize=1)
def get_openai_client():
    if not OPENAI_API_KEY:
        raise MissingKeyError(
            "OPENAI_API_KEY is not set. Add it to your .env file and restart the app."
        )
    from openai import OpenAI

    return OpenAI(api_key=OPENAI_API_KEY)


@lru_cache(maxsize=1)
def get_pinecone_index():
    """Return the Pinecone index, or None when Pinecone isn't configured."""
    if not PINECONE_API_KEY:
        return None
    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=PINECONE_API_KEY)
    if not pc.has_index(PINECONE_INDEX_NAME):
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
    return pc.Index(PINECONE_INDEX_NAME)


def service_status() -> dict[str, bool]:
    """Which services are set up. Shown as status pills in the app header."""
    return {
        "OpenAI": bool(OPENAI_API_KEY),
        "Pinecone": bool(PINECONE_API_KEY),
        "Hunter": bool(HUNTER_API_KEY),
        "n8n": bool(N8N_WEBHOOK_URL),
    }
