"""Tests for the deterministic RAG retrieval evaluation helpers."""

import json

import pytest

from services.retrieval_evaluation import load_dataset, score_case


def test_load_dataset_rejects_duplicate_case_ids(tmp_path):
    dataset_path = tmp_path / "duplicate.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "duplicate ids",
                "cases": [
                    {
                        "id": "S01",
                        "group": "single",
                        "query": "first",
                        "expected_filenames": ["a.md"],
                        "blocking": True,
                    },
                    {
                        "id": "S01",
                        "group": "single",
                        "query": "second",
                        "expected_filenames": ["b.md"],
                        "blocking": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate case id"):
        load_dataset(dataset_path)


def test_score_case_reports_document_coverage_duplicates_and_extra_sources():
    case = {
        "id": "M2-01",
        "group": "multi-2",
        "query": "shipping and refund",
        "expected_filenames": ["02-shipping.md", "04-payment.md"],
        "blocking": True,
    }
    hits = [
        {
            "filename": "02-shipping.md",
            "doc_id": "shipping",
            "chunk_index": 0,
            "score": 0.0412,
            "text": "must not be included in evaluation output",
        },
        {
            "filename": "02-shipping.md",
            "doc_id": "shipping",
            "chunk_index": 1,
            "score": 0.0388,
            "text": "must not be included in evaluation output",
        },
        {
            "filename": "05-human-support.md",
            "doc_id": "support",
            "chunk_index": 0,
            "score": 0.0311,
            "text": "must not be included in evaluation output",
        },
    ]

    result = score_case(case, hits, elapsed_ms=12.34)

    assert result["passed"] is False
    assert result["document_recall"] == 0.5
    assert result["document_precision"] == 0.5
    assert result["duplicate_chunk_rate"] == 0.3333
    assert result["missing_filenames"] == ["04-payment.md"]
    assert result["unexpected_filenames"] == ["05-human-support.md"]
    assert result["elapsed_ms"] == 12.34
    assert result["hits"] == [
        {
            "rank": 1,
            "filename": "02-shipping.md",
            "doc_id": "shipping",
            "chunk_index": 0,
            "score": 0.0412,
        },
        {
            "rank": 2,
            "filename": "02-shipping.md",
            "doc_id": "shipping",
            "chunk_index": 1,
            "score": 0.0388,
        },
        {
            "rank": 3,
            "filename": "05-human-support.md",
            "doc_id": "support",
            "chunk_index": 0,
            "score": 0.0311,
        },
    ]
    assert "text" not in json.dumps(result)


def test_score_non_blocking_diagnostic_does_not_fail_gate():
    case = {
        "id": "OOS01",
        "group": "out-of-scope-diagnostic",
        "query": "mars shipping",
        "expected_filenames": [],
        "allowed_filenames": ["01-products.md", "02-shipping.md"],
        "blocking": False,
    }

    result = score_case(case, [], elapsed_ms=1.0)

    assert result["passed"] is None
    assert result["document_recall"] is None
    assert result["document_precision"] is None


def test_score_case_requires_exact_tokens_without_exposing_text():
    case = {
        "id": "E-SKU-01",
        "group": "exact-product-id",
        "query": "AST-X1-65",
        "expected_filenames": ["01-products.md"],
        "required_tokens": ["AST-X1-65", "SECOND-TOKEN"],
        "blocking": True,
    }
    hits = [
        {
            "filename": "01-products.md",
            "doc_id": "products",
            "chunk_index": 0,
            "score": 0.9,
            "text": "产品编号：AST-X1-65",
        }
    ]

    result = score_case(case, hits, elapsed_ms=2.0)

    assert result["passed"] is False
    assert result["exact_token_recall"] == 0.5
    assert result["matched_required_tokens"] == ["AST-X1-65"]
    assert result["missing_required_tokens"] == ["SECOND-TOKEN"]
    assert "产品编号" not in json.dumps(result, ensure_ascii=False)
