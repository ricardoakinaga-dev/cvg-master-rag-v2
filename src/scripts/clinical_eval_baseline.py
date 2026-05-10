#!/usr/bin/env python3
"""
Run the current chat pipeline against the veterinary clinical eval set.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    ClinicalEvaluationDataset,
    ClinicalExpectedFixture,
    ClinicalExpectedFixtureSet,
    QueryRequest,
    QueryResponse,
)
from services.search_service import search_and_answer


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = ROOT_DIR / "docs/03_build/VCHAT_EVALS/clinical_eval_v1.json"
DEFAULT_FIXTURE_PATH = ROOT_DIR / "docs/03_build/VCHAT_EVALS/clinical_eval_expected_v1.json"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "docs/03_build/VCHAT_EVALS"


def evaluate_response_contract(
    response: QueryResponse,
    fixture: ClinicalExpectedFixture,
) -> dict[str, Any]:
    missing_sections = _missing_sections(response, fixture)
    bibliography_failures = _bibliography_failures(response, fixture)
    guardrail_failures = _guardrail_failures(response, fixture)
    forbidden_patterns = [
        pattern for pattern in fixture.forbidden_response_patterns
        if pattern.lower() in response.answer.lower()
    ]

    failures = []
    failures.extend(f"missing_section:{section}" for section in missing_sections)
    failures.extend(bibliography_failures)
    failures.extend(guardrail_failures)
    failures.extend(f"forbidden_pattern:{pattern}" for pattern in forbidden_patterns)
    if response.low_confidence:
        failures.append("low_confidence:true")

    return {
        "passed": not failures,
        "failures": failures,
        "missing_sections": missing_sections,
        "bibliography_failures": bibliography_failures,
        "guardrail_failures": guardrail_failures,
        "forbidden_patterns": forbidden_patterns,
        "confidence": response.confidence,
        "low_confidence": response.low_confidence,
        "grounded": response.grounded,
        "citation_coverage": response.citation_coverage,
        "chunks_used_count": len(response.chunks_used),
        "citations_count": len(response.citations),
        "latency_ms": response.latency_ms,
    }


def run_baseline(
    dataset: ClinicalEvaluationDataset,
    fixtures: ClinicalExpectedFixtureSet,
    top_k: int,
    threshold: float,
    retrieval_profile: str | None = "clinical_v2",
) -> dict[str, Any]:
    fixture_by_id = {fixture.question_id: fixture for fixture in fixtures.fixtures}
    results = []

    started_at = datetime.now(timezone.utc)
    for question in dataset.questions:
        fixture = fixture_by_id[question.id]
        request = QueryRequest(
            query=question.query,
            workspace_id=question.workspace_id,
            top_k=top_k,
            threshold=threshold,
            retrieval_profile=retrieval_profile,
        )
        response = search_and_answer(request)
        evaluation = evaluate_response_contract(response, fixture)
        results.append({
            "question_id": question.id,
            "query": question.query,
            "clinical_problem": question.clinical_problem,
            "species": question.species,
            "answer_preview": " ".join(response.answer.split())[:500],
            **evaluation,
        })

    finished_at = datetime.now(timezone.utc)
    return _build_report(
        dataset=dataset,
        started_at=started_at,
        finished_at=finished_at,
        top_k=top_k,
        threshold=threshold,
        retrieval_profile=retrieval_profile,
        results=results,
    )


def load_dataset(path: Path) -> ClinicalEvaluationDataset:
    return ClinicalEvaluationDataset(**json.loads(path.read_text(encoding="utf-8")))


def load_fixtures(path: Path) -> ClinicalExpectedFixtureSet:
    return ClinicalExpectedFixtureSet(**json.loads(path.read_text(encoding="utf-8")))


def write_report_files(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = report["started_at"].replace(":", "").replace("-", "")
    report_name = (
        "clinical_v2_eval"
        if report.get("retrieval_profile") == "clinical_v2"
        else "clinical_baseline_current_chat"
    )
    json_path = output_dir / f"{report_name}_{timestamp}.json"
    markdown_path = output_dir / f"{report_name}_{timestamp}.md"
    latest_json = output_dir / f"{report_name}_latest.json"
    latest_markdown = output_dir / f"{report_name}_latest.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    markdown_text = format_markdown_report(report)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    latest_json.write_text(json_text + "\n", encoding="utf-8")
    latest_markdown.write_text(markdown_text, encoding="utf-8")
    return json_path, markdown_path


def format_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Clinical Chat Baseline - Current Chat",
        "",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- dataset_id: {report['dataset_id']}",
        f"- retrieval_profile: {report.get('retrieval_profile')}",
        f"- total_questions: {summary['total_questions']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        f"- missing_sections_count: {summary['missing_sections_count']}",
        f"- bibliography_failure_count: {summary['bibliography_failure_count']}",
        f"- guardrail_failure_count: {summary['guardrail_failure_count']}",
        f"- low_confidence_count: {summary['low_confidence_count']}",
        "",
        "## Results",
        "",
    ]
    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.extend([
            f"### {result['question_id']} - {status}",
            f"- problem: {result['clinical_problem']}",
            f"- species: {result['species']}",
            f"- confidence: {result['confidence']}",
            f"- low_confidence: {result['low_confidence']}",
            f"- grounded: {result['grounded']}",
            f"- citation_coverage: {result['citation_coverage']}",
            f"- chunks_used_count: {result['chunks_used_count']}",
            f"- failures: {', '.join(result['failures']) if result['failures'] else 'none'}",
            f"- answer_preview: {result['answer_preview']}",
            "",
        ])
    return "\n".join(lines)


def _missing_sections(
    response: QueryResponse,
    fixture: ClinicalExpectedFixture,
) -> list[str]:
    if response.sections is None:
        return list(fixture.required_sections)
    section_values = response.sections.model_dump()
    missing = []
    for section in fixture.required_sections:
        if section in fixture.allowed_missing_sections:
            continue
        value = section_values.get(section)
        if not value:
            missing.append(section)
    return missing


def _bibliography_failures(
    response: QueryResponse,
    fixture: ClinicalExpectedFixture,
) -> list[str]:
    failures = []
    if not response.bibliography_footer:
        failures.append("bibliography_footer:missing")
    elif fixture.required_footer_heading not in response.bibliography_footer:
        failures.append("bibliography_footer:missing_heading")
    if len(response.bibliography) < fixture.min_bibliography_references:
        failures.append("bibliography:min_references")

    for reference in response.bibliography:
        dumped = reference.model_dump()
        for field in fixture.required_reference_fields:
            if not dumped.get(field):
                failures.append(f"bibliography_reference:{field}:missing")
    return sorted(set(failures))


def _guardrail_failures(
    response: QueryResponse,
    fixture: ClinicalExpectedFixture,
) -> list[str]:
    if response.guardrails is None:
        return [f"guardrail:{guardrail}:missing" for guardrail in fixture.required_guardrails]
    dumped = response.guardrails.model_dump()
    failures = []
    for guardrail in fixture.required_guardrails:
        if guardrail not in dumped:
            failures.append(f"guardrail:{guardrail}:missing")
        elif guardrail == "unsupported_claims" and dumped[guardrail]:
            failures.append("guardrail:unsupported_claims:not_empty")
        elif guardrail != "unsupported_claims" and dumped[guardrail] is not True:
            failures.append(f"guardrail:{guardrail}:false")
    return failures


def _build_report(
    dataset: ClinicalEvaluationDataset,
    started_at: datetime,
    finished_at: datetime,
    top_k: int,
    threshold: float,
    retrieval_profile: str | None,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_id": dataset.dataset_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "top_k": top_k,
        "threshold": threshold,
        "retrieval_profile": retrieval_profile,
        "summary": {
            "total_questions": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "failed": sum(1 for result in results if not result["passed"]),
            "missing_sections_count": sum(len(result["missing_sections"]) for result in results),
            "bibliography_failure_count": sum(len(result["bibliography_failures"]) for result in results),
            "guardrail_failure_count": sum(len(result["guardrail_failures"]) for result in results),
            "low_confidence_count": sum(1 for result in results if result["low_confidence"]),
        },
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clinical chat baseline against current pipeline")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--threshold", type=float, default=0.25)
    parser.add_argument("--retrieval-profile", default="clinical_v2")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = time.time()
    dataset = load_dataset(args.dataset)
    fixtures = load_fixtures(args.fixtures)
    report = run_baseline(
        dataset,
        fixtures,
        top_k=args.top_k,
        threshold=args.threshold,
        retrieval_profile=args.retrieval_profile or None,
    )
    json_path, markdown_path = write_report_files(report, args.output_dir)
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Elapsed {time.time() - start:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
