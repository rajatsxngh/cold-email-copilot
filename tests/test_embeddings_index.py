from types import SimpleNamespace

import pytest

from src import config, embeddings_index
from src.embeddings_index import chunk_text, find_relevant_snippets, split_resume

from .conftest import SAMPLE_JD, SAMPLE_RESUME_LINES


@pytest.mark.parametrize("word_count", [0, 1, 44, 45, 46, 100, 701])
def test_chunk_text_finishes_and_keeps_every_word(word_count):
    words = [f"w{i}" for i in range(word_count)]
    chunks = chunk_text(" ".join(words), size=45, overlap=10)
    covered = {w for chunk in chunks for w in chunk.split()}
    assert covered == set(words)
    assert all(len(c.split()) <= 45 for c in chunks)


def test_chunk_text_rejects_overlap_as_big_as_size():
    with pytest.raises(ValueError):
        chunk_text("a b c", size=10, overlap=10)


def test_split_resume_gives_one_piece_per_sentence_or_bullet():
    text = (
        "Experience\n"
        "• Built SQL pipelines for the operations team\nacross three warehouses\n"
        "• Created Power BI dashboards for the sales team. Presented them to leadership every week.\n"
        "• Won an award. Led a team of five analysts on a pricing project."
    )
    pieces = split_resume(text)
    assert pieces == [
        "Experience Built SQL pipelines for the operations team across three warehouses",
        "Created Power BI dashboards for the sales team.",
        "Presented them to leadership every week.",
        "Won an award. Led a team of five analysts on a pricing project.",  # short bits join the next piece
    ]


def test_split_resume_cuts_very_long_sentences():
    long_sentence = " ".join(f"word{i}" for i in range(120))
    pieces = split_resume(long_sentence)
    assert len(pieces) > 1
    assert all(len(p.split()) <= embeddings_index.CHUNK_SIZE for p in pieces)


def test_in_memory_search_ranks_relevant_lines_first(fake_models):
    snippets, source = find_relevant_snippets("\n\n".join(SAMPLE_RESUME_LINES), SAMPLE_JD, top_k=3)
    assert source == "in-memory"
    assert len(snippets) == 3
    assert all("holiday party" not in s["text"] for s in snippets)
    assert snippets == sorted(snippets, key=lambda s: s["score"], reverse=True)


def test_empty_inputs_return_nothing(fake_models):
    assert find_relevant_snippets("", SAMPLE_JD) == ([], "none")
    assert find_relevant_snippets("Some resume text here today", "   ") == ([], "none")


class FakeIndex:
    def __init__(self, return_matches=True):
        self.calls = []
        self.vectors = []
        self.return_matches = return_matches

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))

    def upsert(self, **kwargs):
        self.calls.append(("upsert", kwargs))
        self.vectors = kwargs["vectors"]

    def query(self, **kwargs):
        self.calls.append(("query", kwargs))
        if not self.return_matches:
            return SimpleNamespace(matches=[])
        return SimpleNamespace(matches=[SimpleNamespace(metadata=v["metadata"]) for v in self.vectors])


def test_pinecone_replaces_old_resume_and_searches_only_the_new_one(fake_models, monkeypatch):
    index = FakeIndex()
    monkeypatch.setattr(config, "get_pinecone_index", lambda: index)

    snippets, source = find_relevant_snippets("\n\n".join(SAMPLE_RESUME_LINES), SAMPLE_JD, user_id="u1")

    assert source == "pinecone" and snippets
    kinds = [kind for kind, _ in index.calls]
    assert kinds[:3] == ["delete", "upsert", "query"]
    delete_args, upsert_args, query_args = (args for _, args in index.calls[:3])
    assert delete_args == {"delete_all": True, "namespace": "resume-u1"}
    assert upsert_args["namespace"] == "resume-u1"
    resume_id = upsert_args["vectors"][0]["metadata"]["resume_id"]
    assert query_args["filter"] == {"resume_id": {"$eq": resume_id}}


def test_falls_back_to_in_memory_when_pinecone_has_no_results_yet(fake_models, monkeypatch):
    index = FakeIndex(return_matches=False)
    monkeypatch.setattr(config, "get_pinecone_index", lambda: index)
    snippets, source = find_relevant_snippets("\n\n".join(SAMPLE_RESUME_LINES), SAMPLE_JD)
    assert source == "in-memory" and snippets
    assert [kind for kind, _ in index.calls].count("query") == len(embeddings_index.PINECONE_RETRY_DELAYS)


def test_falls_back_to_in_memory_when_pinecone_errors(fake_models, monkeypatch):
    class BrokenIndex(FakeIndex):
        def upsert(self, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr(config, "get_pinecone_index", lambda: BrokenIndex())
    snippets, source = find_relevant_snippets("\n\n".join(SAMPLE_RESUME_LINES), SAMPLE_JD)
    assert source == "in-memory" and snippets
