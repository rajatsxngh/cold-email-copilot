# src/embeddings_index.py
"""Find the parts of your resume that best match a job description.

How it works:
1. Split the resume into sentences and bullet points (long ones are cut into
   smaller, overlapping pieces), so each match is a line you can read.
2. Turn each chunk into an embedding (a list of numbers that captures meaning).
3. Save the chunks in Pinecone and search them with the job description.
4. Re-rank the best candidates with a cross-encoder, which reads the job
   description and each chunk together and gives a more accurate score.

If Pinecone isn't set up, or hasn't finished saving the new chunks yet, the
search runs in memory instead, so you always get results.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from functools import lru_cache

import numpy as np

from . import config

log = logging.getLogger(__name__)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

CHUNK_SIZE = 45  # most words in one piece; longer sentences get split
CHUNK_OVERLAP = 10  # words shared by neighbouring pieces when a long sentence is split
MIN_PIECE_WORDS = 5  # shorter bits (like section headings) are joined to the next piece
CANDIDATES = 20  # pieces fetched before re-ranking
PINECONE_RETRY_DELAYS = (0.0, 1.5, 3.0)  # new vectors can take a moment to become searchable


@lru_cache(maxsize=1)
def get_embed_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL_NAME)


@lru_cache(maxsize=1)
def get_rerank_model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANK_MODEL_NAME)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks of `size` words, each sharing `overlap` words with the last."""
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")
    words = text.split()
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks


BULLET_CHARS = "•▪●◦‣∙"
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z])")


def split_resume(text: str) -> list[str]:
    """Split resume text into readable pieces: sentences and bullet points.

    Very short bits (like "Experience") are joined to the next piece, and very
    long ones are cut into overlapping chunks of CHUNK_SIZE words.
    """
    text = re.sub(f"[{BULLET_CHARS}]", "\n\n", text)
    pieces: list[str] = []
    carry = ""
    for block in re.split(r"\n\s*\n", text):  # bullets and blank lines start new pieces
        block = " ".join(block.split())  # undo line wrapping from the PDF
        for sentence in SENTENCE_END.split(block):
            sentence = f"{carry} {sentence}".strip()
            if len(sentence.split()) < MIN_PIECE_WORDS:
                carry = sentence
                continue
            carry = ""
            if len(sentence.split()) > CHUNK_SIZE:
                pieces.extend(chunk_text(sentence))
            else:
                pieces.append(sentence)
    if carry:
        pieces.append(carry)
    return pieces


def _embed(texts: list[str]) -> np.ndarray:
    return get_embed_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)


def _namespace(user_id: str) -> str:
    return f"resume-{user_id}"


def _save_to_pinecone(index, chunks, embeddings, user_id: str, resume_id: str) -> None:
    """Replace this user's stored resume with the new one."""
    namespace = _namespace(user_id)
    try:
        index.delete(delete_all=True, namespace=namespace)
    except Exception:  # the namespace doesn't exist yet on a first run
        pass
    vectors = [
        {
            "id": f"{resume_id}-{i}",
            "values": emb.tolist(),
            "metadata": {"text": chunk, "resume_id": resume_id},
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    index.upsert(vectors=vectors, namespace=namespace, show_progress=False)


def _search_pinecone(index, jd_embedding, user_id: str, resume_id: str) -> list[str]:
    """Query Pinecone, retrying briefly while freshly saved chunks become searchable."""
    for delay in PINECONE_RETRY_DELAYS:
        time.sleep(delay)
        res = index.query(
            vector=jd_embedding.tolist(),
            top_k=CANDIDATES,
            namespace=_namespace(user_id),
            include_metadata=True,
            # only this resume, even if an older one hasn't been deleted yet
            filter={"resume_id": {"$eq": resume_id}},
        )
        texts = [m.metadata["text"] for m in res.matches if m.metadata]
        if texts:
            return texts
    return []


def _search_in_memory(chunks, embeddings, jd_embedding) -> list[str]:
    scores = embeddings @ jd_embedding  # cosine similarity (embeddings are normalized)
    best = np.argsort(-scores)[:CANDIDATES]
    return [chunks[i] for i in best]


def _rerank(jd_text: str, candidates: list[str], top_k: int) -> list[dict]:
    import torch

    scores = get_rerank_model().predict(
        [(jd_text, c) for c in candidates], activation_fn=torch.nn.Sigmoid()
    )
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [{"text": text, "score": float(score)} for text, score in ranked[:top_k]]


def find_relevant_snippets(
    resume_text: str, jd_text: str, user_id: str = "user1", top_k: int = 5
) -> tuple[list[dict], str]:
    """Return the resume chunks that best match the job description.

    Returns (snippets, source). Each snippet is {"text": ..., "score": 0-1}.
    `source` is "pinecone" or "in-memory", depending on where the search ran.
    """
    chunks = split_resume(resume_text)
    if not chunks or not jd_text.strip():
        return [], "none"

    embeddings = _embed(chunks)
    jd_embedding = _embed([jd_text])[0]
    resume_id = hashlib.sha1(resume_text.encode("utf-8")).hexdigest()[:12]

    candidates: list[str] = []
    source = "in-memory"
    index = config.get_pinecone_index()
    if index is not None:
        try:
            _save_to_pinecone(index, chunks, embeddings, user_id, resume_id)
            candidates = _search_pinecone(index, jd_embedding, user_id, resume_id)
            source = "pinecone"
        except Exception as exc:
            log.warning("Pinecone failed, using in-memory search instead: %s", exc)
    if not candidates:
        candidates = _search_in_memory(chunks, embeddings, jd_embedding)
        source = "in-memory"

    return _rerank(jd_text, candidates, top_k), source
