"""Run the golden-dataset evaluation and write reports to evaluation/reports/.

Usage (from backend/):
    python -m scripts.run_evaluation                       # full run when GOOGLE_API_KEY is set, else retrieval-only
    python -m scripts.run_evaluation --mode retrieval_only # no LLM calls
"""
import argparse

from app.api.deps import build_container
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["full", "retrieval_only"], default=None)
    args = parser.parse_args()

    settings = get_settings()
    configure_logging("WARNING", settings.secret_values())
    container = build_container(settings)
    try:
        container.schema_service.ensure_index()
        report = container.evaluation_service.run(args.mode)
    except AppError as exc:
        print(f"Evaluation failed: {exc.message}")
        return 1
    print(f"mode={report.mode} questions={report.metrics['questions_total']} adversarial={report.metrics['adversarial_cases']}")
    for key, value in report.metrics.items():
        print(f"  {key}: {value}")
    for note in report.notes:
        print(f"  note: {note}")
    print(f"report written to {settings.evaluation_reports_dir}/latest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
