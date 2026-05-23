"""Unit tests for the cohort vocabulary extractor + filter."""
import pytest


def test_build_vocabularies_dedups_and_sorts():
    """build_vocabularies returns three deduped sorted lists keyed by kind."""
    from src.db.mongo import build_vocabularies

    docs = [
        {"conditions":  {"active": [{"condition": "Hypertension", "code": "59621000"},
                                     {"condition": "T2DM",         "code": "44054006"}]},
         "medications": {"active": [{"medication": "Metformin", "rx_code": "861007"}]},
         "labs":        {"latest_labs": [{"test_name": "HbA1c"},
                                         {"test_name": "LDL cholesterol"}]}},
        {"conditions":  {"active": [{"condition": "Hypertension", "code": "59621000"}]},
         "medications": {"active": [{"medication": "Lisinopril", "rx_code": "29046"}]},
         "labs":        {"latest_labs": [{"test_name": "HbA1c"}]}},
    ]
    vocab = build_vocabularies(docs)

    assert vocab["condition"] == [
        {"label": "Hypertension", "code": "59621000"},
        {"label": "T2DM",         "code": "44054006"},
    ]
    assert vocab["medication"] == [
        {"label": "Lisinopril", "code": "29046"},
        {"label": "Metformin",  "code": "861007"},
    ]
    assert vocab["lab"] == [
        {"label": "HbA1c",           "code": None},
        {"label": "LDL cholesterol", "code": None},
    ]


def test_filter_vocabulary_exact_prefix_first():
    """filter_vocabulary returns prefix-matches before substring-matches."""
    from src.db.mongo import filter_vocabulary

    vocab = [
        {"label": "Ametformin XR", "code": "1"},   # substring match
        {"label": "Metformin",     "code": "2"},   # prefix match
        {"label": "Metformin XR",  "code": "3"},   # prefix match
        {"label": "Aspirin",       "code": "4"},   # no match
    ]
    out = filter_vocabulary(vocab, "metf", limit=20)
    labels = [it["label"] for it in out]
    assert labels == ["Metformin", "Metformin XR", "Ametformin XR"]


def test_filter_vocabulary_empty_query_returns_first_n():
    """Empty q returns the first `limit` items alphabetically."""
    from src.db.mongo import filter_vocabulary
    vocab = [{"label": f"item{i:03d}", "code": str(i)} for i in range(30)]
    out = filter_vocabulary(vocab, "", limit=5)
    assert [it["label"] for it in out] == ["item000","item001","item002","item003","item004"]


def test_filter_vocabulary_case_insensitive():
    from src.db.mongo import filter_vocabulary
    vocab = [{"label": "Metformin", "code": "x"}]
    assert filter_vocabulary(vocab, "METF", limit=5)[0]["label"] == "Metformin"
    assert filter_vocabulary(vocab, "metf", limit=5)[0]["label"] == "Metformin"
