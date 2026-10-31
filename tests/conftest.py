"""Shared test helpers. Every outside service (OpenAI, Pinecone, Hunter, n8n and the
Hugging Face models) is replaced with a small fake, so tests run offline with no keys."""
import hashlib
import json
import re
from types import SimpleNamespace

import numpy as np
import pytest

from src import config, embeddings_index


class FakeEmbedModel:
    """Turns text into a bag-of-words vector, so similar words give similar vectors."""

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        vectors = []
        for text in texts:
            v = np.zeros(config.EMBEDDING_DIMENSION)
            for word in re.findall(r"[a-z]+", text.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % len(v)] += 1
            norm = np.linalg.norm(v)
            vectors.append(v / norm if norm else v)
        return np.array(vectors)


class FakeRerankModel:
    """Scores a (job, resume line) pair by how many words they share."""

    def predict(self, pairs, activation_fn=None):
        scores = []
        for jd, chunk in pairs:
            jd_words = set(re.findall(r"[a-z]{3,}", jd.lower()))
            chunk_words = set(re.findall(r"[a-z]{3,}", chunk.lower()))
            scores.append(len(jd_words & chunk_words) / max(1, len(chunk_words)))
        return np.array(scores)


class FakeOpenAI:
    """Returns queued replies, one per call, and records each request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture(autouse=True)
def no_real_services(monkeypatch):
    """Start every test with no keys set, so nothing can reach a real service."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "PINECONE_API_KEY", "")
    monkeypatch.setattr(config, "HUNTER_API_KEY", "")
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "")
    monkeypatch.setattr(config, "get_pinecone_index", lambda: None)
    monkeypatch.setattr(embeddings_index, "PINECONE_RETRY_DELAYS", (0, 0, 0))


@pytest.fixture
def fake_models(monkeypatch):
    monkeypatch.setattr(embeddings_index, "get_embed_model", lambda: FakeEmbedModel())
    monkeypatch.setattr(embeddings_index, "get_rerank_model", lambda: FakeRerankModel())


@pytest.fixture
def fake_openai(monkeypatch):
    """Call fake_openai([reply1, reply2, ...]) to set what the 'model' answers."""

    def install(replies):
        client = FakeOpenAI(replies)
        monkeypatch.setattr(config, "get_openai_client", lambda: client)
        return client

    return install


def make_pdf(path, lines):
    """Write a small one-page PDF with the given lines of text."""
    text_ops = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines
    ) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text_ops)} >>\nstream\n{text_ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


SAMPLE_RESUME_LINES = [
    "Jordan Patel. Dallas, TX. jordan@example.com",
    "Built SQL pipelines that combined shipment, carrier and warehouse data into one reporting table.",
    "Created Power BI dashboards tracking on-time delivery and cost per mile across 40 routes.",
    "Wrote Python scripts to clean messy carrier invoices, saving about 6 hours each week.",
    "Organized the office holiday party and volunteer food drive for two years.",
]

SAMPLE_JD = (
    "Data Analyst at Northwind Logistics in Dallas. You will write SQL to combine shipment, carrier and "
    "warehouse data, build Power BI dashboards for on-time delivery and cost per mile, and clean carrier "
    "data with Python. Strong SQL and Power BI skills required."
)
