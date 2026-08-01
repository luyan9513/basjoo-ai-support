"""Deterministic retrieval evaluation for document coverage and chunk diversity."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TextIO


RetrievalCallable = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


def _read_dataset_source(source: str | Path | TextIO) -> dict[str, Any]:
    if hasattr(source, "read"):
        data = json.load(source)
    elif str(source) == "-":
        data = json.load(sys.stdin)
    else:
        with Path(source).open(encoding="utf-8") as dataset_file:
            data = json.load(dataset_file)

    if not isinstance(data, dict):
        raise ValueError("dataset must be a JSON object")
    return data


def load_dataset(source: str | Path | TextIO) -> dict[str, Any]:
    """Load and validate the stable fields used by the retrieval evaluator."""
    dataset = _read_dataset_source(source)
    if dataset.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")

    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset cases must be a non-empty list")

    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be a JSON object")

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("case id must be a non-empty string")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError(f"case {case_id} query must be a non-empty string")
        if not isinstance(case.get("group"), str) or not case["group"].strip():
            raise ValueError(f"case {case_id} group must be a non-empty string")
        if not isinstance(case.get("blocking"), bool):
            raise ValueError(f"case {case_id} blocking must be boolean")

        expected = case.get("expected_filenames")
        if not isinstance(expected, list) or any(
            not isinstance(filename, str) or not filename for filename in expected
        ):
            raise ValueError(
                f"case {case_id} expected_filenames must be a list of filenames"
            )
        if len(set(expected)) != len(expected):
            raise ValueError(f"case {case_id} has duplicate expected filenames")

        required_tokens = case.get("required_tokens", [])
        if not isinstance(required_tokens, list) or any(
            not isinstance(token, str) or not token for token in required_tokens
        ):
            raise ValueError(
                f"case {case_id} required_tokens must be a list of strings"
            )
        if len(set(required_tokens)) != len(required_tokens):
            raise ValueError(f"case {case_id} has duplicate required tokens")

        allowed = case.get("allowed_filenames", [])
        if not isinstance(allowed, list) or any(
            not isinstance(filename, str) or not filename for filename in allowed
        ):
            raise ValueError(
                f"case {case_id} allowed_filenames must be a list of filenames"
            )

    return dataset


def _unique_in_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def score_case(
    case: dict[str, Any],
    hits: list[dict[str, Any]],
    elapsed_ms: float,
) -> dict[str, Any]:
    """Score one retrieval run without retaining retrieved text."""
    expected = case["expected_filenames"]
    actual_filenames = _unique_in_order(
        [str(hit.get("filename") or "") for hit in hits]
    )
    matched = [filename for filename in expected if filename in actual_filenames]
    missing = [filename for filename in expected if filename not in actual_filenames]
    unexpected = [
        filename for filename in actual_filenames if filename not in expected
    ]

    required_tokens = case.get("required_tokens", [])
    retrieved_text = "\n".join(str(hit.get("text") or "") for hit in hits).casefold()
    matched_required_tokens = [
        token for token in required_tokens if token.casefold() in retrieved_text
    ]
    missing_required_tokens = [
        token for token in required_tokens if token.casefold() not in retrieved_text
    ]
    exact_token_recall = (
        round(len(matched_required_tokens) / len(required_tokens), 4)
        if required_tokens
        else None
    )

    if expected:
        document_recall: float | None = round(len(matched) / len(expected), 4)
        document_precision: float | None = round(
            len(matched) / len(actual_filenames), 4
        ) if actual_filenames else 0.0
        passed: bool | None = (
            not missing and not missing_required_tokens
            if case["blocking"]
            else None
        )
    else:
        document_recall = None
        document_precision = None
        passed = None

    document_keys = _unique_in_order(
        [
            str(hit.get("doc_id") or hit.get("filename") or f"rank:{rank}")
            for rank, hit in enumerate(hits, start=1)
        ]
    )
    duplicate_chunk_rate = (
        round(1 - len(document_keys) / len(hits), 4) if hits else 0.0
    )

    safe_hits = [
        {
            "rank": rank,
            "filename": hit.get("filename"),
            "doc_id": hit.get("doc_id"),
            "chunk_index": hit.get("chunk_index"),
            "score": hit.get("score"),
        }
        for rank, hit in enumerate(hits, start=1)
    ]

    return {
        "id": case["id"],
        "group": case["group"],
        "blocking": case["blocking"],
        "passed": passed,
        "expected_filenames": expected,
        "retrieved_filenames": actual_filenames,
        "missing_filenames": missing,
        "unexpected_filenames": unexpected,
        "document_recall": document_recall,
        "document_precision": document_precision,
        "matched_required_tokens": matched_required_tokens,
        "missing_required_tokens": missing_required_tokens,
        "exact_token_recall": exact_token_recall,
        "duplicate_chunk_rate": duplicate_chunk_rate,
        "elapsed_ms": round(elapsed_ms, 2),
        "hits": safe_hits,
    }


async def evaluate_dataset(
    dataset: dict[str, Any],
    retrieve: RetrievalCallable,
    *,
    top_k: int,
    repetitions: int,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run selected cases and aggregate only deterministic retrieval metrics."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    cases = [
        case
        for case in dataset["cases"]
        if case_ids is None or case["id"] in case_ids
    ]
    if not cases:
        raise ValueError("no evaluation cases selected")

    runs: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            hits = await retrieve(case["query"], top_k)
            elapsed_ms = (time.perf_counter() - started) * 1000
            scored = score_case(case, hits, elapsed_ms)
            scored["repetition"] = repetition
            runs.append(scored)

    blocking_runs = [run for run in runs if run["blocking"]]
    recalls = [
        run["document_recall"]
        for run in blocking_runs
        if run["document_recall"] is not None
    ]
    passed_runs = sum(run["passed"] is True for run in blocking_runs)
    exact_token_recalls = [
        run["exact_token_recall"]
        for run in blocking_runs
        if run["exact_token_recall"] is not None
    ]

    stability: dict[str, bool] = {}
    for case in cases:
        filename_sets = {
            tuple(run["retrieved_filenames"])
            for run in runs
            if run["id"] == case["id"]
        }
        stability[case["id"]] = len(filename_sets) == 1

    return {
        "dataset": dataset.get("name"),
        "schema_version": dataset["schema_version"],
        "top_k": top_k,
        "repetitions": repetitions,
        "summary": {
            "selected_cases": len(cases),
            "total_runs": len(runs),
            "blocking_runs": len(blocking_runs),
            "passed_blocking_runs": passed_runs,
            "all_blocking_passed": passed_runs == len(blocking_runs),
            "macro_document_recall": round(sum(recalls) / len(recalls), 4)
            if recalls
            else None,
            "macro_exact_token_recall": round(
                sum(exact_token_recalls) / len(exact_token_recalls), 4
            )
            if exact_token_recalls
            else None,
            "stable_cases": sum(stability.values()),
        },
        "stability": stability,
        "runs": runs,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate Basjoo retrieval document coverage without outputting chunk text."
    )
    parser.add_argument("--dataset", required=True, help="JSON path or '-' for stdin")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only this case ID; may be repeated",
    )
    return parser


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    from services.kb_retrieval_service import KbRetrievalService

    dataset = load_dataset(args.dataset)
    service = KbRetrievalService()

    async def retrieve(query: str, top_k: int) -> list[dict[str, Any]]:
        return await service.retrieve(
            tenant_id=None,
            agent_id=args.agent_id,
            query=query,
            top_k=top_k,
        )

    return await evaluate_dataset(
        dataset,
        retrieve,
        top_k=args.top_k,
        repetitions=args.repetitions,
        case_ids=set(args.case_ids) if args.case_ids else None,
    )


def main() -> None:
    args = _build_parser().parse_args()
    report = asyncio.run(_run_cli(args))
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
