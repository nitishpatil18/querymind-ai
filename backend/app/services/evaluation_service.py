"""Evaluation framework: runs the golden dataset and reports only measured numbers.

Metrics that need the LLM are reported as null (not estimated) when the LLM is not configured.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.core.errors import (
    AppError,
    BadRequestError,
    LLMModelNotFoundError,
    LLMOverloadedError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.execution_service import ExecutionService
from app.services.query_service import QueryService
from app.services.schema_service import SchemaService
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- dataset models
class EvalQuestion(BaseModel):
    id: str
    category: str
    question: str
    expected_sql: str | None = None
    expected_tables: list[str] = Field(default_factory=list)
    expected_behavior: Literal["answer", "clarify_or_assume", "refuse"] = "answer"
    scoring: Literal["result", "executes"] = "result"  # "executes": definition is open, only validity/execution count
    ordered: bool = False
    notes: str | None = None


class AdversarialCase(BaseModel):
    id: str
    sql: str
    why: str


class EvalDataset(BaseModel):
    version: int = 1
    description: str = ""
    questions: list[EvalQuestion]
    adversarial_sql: list[AdversarialCase] = Field(default_factory=list)


# --------------------------------------------------------------------------- report models
class QuestionResult(BaseModel):
    id: str
    category: str
    question: str
    expected_behavior: str
    status: str | None = None  # pipeline status, or "error"
    generated_sql: str | None = None
    sql_valid: bool | None = None
    executed: bool | None = None
    execution_match: bool | None = None  # None when not applicable
    execution_match_extra_columns: bool | None = None  # like execution_match, but extra columns in the answer are allowed
    exact_sql_match: bool | None = None
    behavior_ok: bool | None = None  # for refuse / clarify_or_assume questions
    retrieved_tables: list[str] = Field(default_factory=list)
    semantic_tables: list[str] = Field(default_factory=list)
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    recall_expanded: float | None = None
    precision_expanded: float | None = None
    generation_ms: float | None = None
    retrieval_ms: float | None = None
    execution_ms: float | None = None
    attempts: int | None = None
    assumptions: list[str] = Field(default_factory=list)
    error: str | None = None
    llm_model: str | None = None  # model that produced this answer (runs can be resumed with another model)


class AdversarialResult(BaseModel):
    id: str
    sql: str
    why: str
    rejected_by_validator: bool
    blocked_end_to_end: bool
    rule: str | None = None


class EvalReport(BaseModel):
    run_id: str
    mode: str  # "full" | "retrieval_only"
    started_at: datetime
    finished_at: datetime
    llm_provider: str | None
    llm_model: str | None
    embedding_provider: str
    embedding_model: str
    retrieval_top_k: int
    retrieval_max_tables: int
    schema_fingerprint: str
    dataset_version: int
    metrics: dict[str, Any]
    by_category: dict[str, dict[str, Any]]
    results: list[QuestionResult]
    adversarial: list[AdversarialResult]
    golden_sql_check: dict[str, Any]
    notes: list[str] = Field(default_factory=list)


class EvalProgress(BaseModel):
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    started_at: datetime | None = None
    completed: int = 0
    total: int = 0
    current: str | None = None
    error: str | None = None
    mode: str | None = None


# --------------------------------------------------------------------------- result comparison
_ISO_MONTH = re.compile(r"^\d{4}-\d{2}$")
_ISO_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]00:00:00(?:\+00:00|Z)?$")


def _norm_value(v: Any) -> str:
    if v is None:
        return "∅"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float, Decimal)):
        f = float(v)
        return str(int(f)) if f == int(f) and abs(f) < 1e15 else f"{round(f, 2):.2f}".rstrip("0").rstrip(".")
    if isinstance(v, (date, datetime)):
        v = v.isoformat()
    s = str(v).strip()
    if m := _ISO_TS.match(s):
        s = m.group(1)
    if _ISO_MONTH.match(s):
        s += "-01"
    return s


def normalise_rows(rows: list[list[Any]]) -> list[tuple[str, ...]]:
    """Order-insensitive within a row so column order/aliases do not matter."""
    return [tuple(sorted(_norm_value(v) for v in row)) for row in rows]


def results_match(expected: list[list[Any]], actual: list[list[Any]], ordered: bool) -> bool:
    if len(expected) != len(actual):
        return False
    if expected and actual and len(expected[0]) != len(actual[0]):
        return False
    a, b = normalise_rows(expected), normalise_rows(actual)
    return a == b if ordered else sorted(a) == sorted(b)


def results_match_allowing_extra_columns(expected: list[list[Any]], actual: list[list[Any]], ordered: bool) -> bool:
    """True when some choice of columns from `actual` reproduces `expected` exactly (extra columns are ignored).

    A query that adds an id column the question did not ask for still answers the question; the strict
    metric stays available so neither number hides the other.
    """
    from itertools import combinations

    if len(expected) != len(actual):
        return False
    if not expected:
        return True
    width, have = len(expected[0]), len(actual[0]) if actual else 0
    if have < width:
        return False
    for n, cols in enumerate(combinations(range(have), width)):
        if n > 5000:  # very wide results: give up rather than search forever
            return False
        if results_match(expected, [[row[i] for i in cols] for row in actual], ordered):
            return True
    return False


def _norm_sql(sql: str | None, validator: ValidationService) -> str | None:
    if not sql:
        return None
    r = validator.validate(sql, None)
    return " ".join((r.normalized_sql or sql).lower().split()) if r.valid else None


def _prf(expected: list[str], got: list[str]) -> tuple[float | None, float | None]:
    if not expected:
        return None, None
    e, g = {t.lower() for t in expected}, {t.lower() for t in got}
    inter = len(e & g)
    return inter / len(e), (inter / len(g) if g else 0.0)


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


# --------------------------------------------------------------------------- service
class EvaluationService:
    def __init__(
        self,
        query_service: QueryService,
        schema_service: SchemaService,
        executor: ExecutionService,
        validator: ValidationService,
        settings: Settings | None = None,
        rate_limit_retries: int = 6,
        sleep=time.sleep,
    ):
        self.qs = query_service
        self.schema_service = schema_service
        self.executor = executor
        self.validator = validator
        self.settings = settings or get_settings()
        self.rate_limit_retries = rate_limit_retries
        self._sleep = sleep
        self._rate_limited_questions = 0  # consecutive questions that stayed rate limited after all retries
        self._model_blocked = False
        self._overloaded_questions = 0
        self.progress = EvalProgress()
        self._lock = threading.Lock()
        self.settings.evaluation_reports_dir.mkdir(parents=True, exist_ok=True)

    # -- dataset --------------------------------------------------------------------
    def load_dataset(self) -> EvalDataset:
        path = self.settings.golden_questions_path
        try:
            return EvalDataset.model_validate_json(Path(path).read_text())
        except FileNotFoundError as exc:
            raise BadRequestError("The golden evaluation dataset was not found.") from exc

    # -- async API ------------------------------------------------------------------
    def start_background(self, mode: str | None = None, resume: bool = False) -> EvalProgress:
        with self._lock:
            if self.progress.status == "running":
                return self.progress
            dataset = self.load_dataset()
            self.progress = EvalProgress(status="running", started_at=datetime.now(timezone.utc), total=len(dataset.questions), mode=mode or self.default_mode())
        threading.Thread(target=self._run_safely, args=(mode, resume), daemon=True, name="evaluation").start()
        return self.progress

    def _run_safely(self, mode: str | None, resume: bool = False) -> None:
        try:
            self.run(mode, resume=resume)
        except Exception as exc:  # recorded for the dashboard; details stay in the log
            logger.exception("evaluation run failed")
            self.progress = self.progress.model_copy(update={"status": "failed", "error": getattr(exc, "message", "Evaluation failed.")})

    def latest(self) -> EvalReport | None:
        f = self.settings.evaluation_reports_dir / "latest.json"
        try:
            return EvalReport.model_validate_json(f.read_text())
        except Exception:
            return None

    def default_mode(self) -> str:
        return "full" if self.settings.llm_configured else "retrieval_only"

    # -- run --------------------------------------------------------------------------
    def run(self, mode: str | None = None, resume: bool = False) -> EvalReport:
        mode = mode or self.default_mode()
        if mode == "full" and not self.settings.llm_configured:
            raise BadRequestError("A full evaluation needs an LLM. Set GOOGLE_API_KEY, or run with mode=retrieval_only.")
        dataset = self.load_dataset()
        schema = self.schema_service.get_schema()
        self.schema_service.ensure_index()
        started = datetime.now(timezone.utc)
        self.progress = EvalProgress(status="running", started_at=started, total=len(dataset.questions), mode=mode)

        self._rate_limited_questions, self._overloaded_questions, self._model_blocked = 0, 0, False
        golden = self._check_golden_sql(dataset)
        kept = self._carried_over(dataset, mode, schema.fingerprint) if resume else {}
        results: list[QuestionResult] = []
        for i, q in enumerate(dataset.questions, start=1):
            self.progress = self.progress.model_copy(update={"completed": i - 1, "current": q.id})
            results.append(kept[q.id] if q.id in kept else self._run_question(q, dataset, mode))
        adversarial = self._run_adversarial(dataset)

        report = self._build_report(mode, dataset, results, adversarial, golden, started, schema.fingerprint)
        if kept:
            models = sorted({r.llm_model or "earlier runs (model not recorded)" for r in results if r.status != "error" and r.llm_model != self.settings.llm_model} | {self.settings.llm_model})
            report.notes.append(
                f"Resumed run: {len(kept)} answers were carried over from earlier runs and {len(dataset.questions) - len(kept)} were run now. "
                f"Models involved: {', '.join(models)}."
            )
        self._persist(report)
        self.progress = self.progress.model_copy(update={"status": "completed", "completed": len(dataset.questions), "current": None})
        return report

    # -- helpers ------------------------------------------------------------------------
    def _carried_over(self, dataset: EvalDataset, mode: str, fingerprint: str) -> dict[str, QuestionResult]:
        """Answers from the previous run that are still valid: same mode, dataset and schema, and no provider error."""
        prev = self.latest()
        if not prev or prev.mode != mode or prev.dataset_version != dataset.version or prev.schema_fingerprint != fingerprint:
            return {}
        by_id = {q.id: q for q in dataset.questions}
        kept = {r.id: r for r in prev.results if r.id in by_id and r.status != "error"}
        for r in kept.values():
            self._backfill_extra_columns(by_id[r.id], r)
        return kept

    def _backfill_extra_columns(self, q: EvalQuestion, res: QuestionResult) -> None:
        """Answers saved before the lenient metric existed have no value for it. Compute it from the stored SQL
        (a read-only query, no model call) so old and new answers are scored the same way."""
        if res.execution_match is None or res.execution_match_extra_columns is not None:
            return
        if res.execution_match:
            res.execution_match_extra_columns = True
            return
        if not (res.generated_sql and q.expected_sql):
            return
        try:
            expected = self.executor.execute(q.expected_sql, max_rows=self.settings.max_result_rows)
            actual = self.executor.execute(res.generated_sql, max_rows=self.settings.max_result_rows)
            res.execution_match_extra_columns = results_match_allowing_extra_columns(expected.rows, actual.rows, q.ordered)
        except AppError:
            logger.warning("could not recompute the extra-columns check", extra={"question_id": q.id})

    def _check_golden_sql(self, dataset: EvalDataset) -> dict[str, Any]:
        """Sanity-check the dataset itself: every expected query must validate and run."""
        total = ok_valid = ok_exec = 0
        failures: list[str] = []
        for q in dataset.questions:
            if not q.expected_sql:
                continue
            total += 1
            v = self.validator.validate(q.expected_sql, self.schema_service.get_schema())
            if v.valid:
                ok_valid += 1
                try:
                    self.executor.execute(q.expected_sql, max_rows=self.settings.max_result_rows)
                    ok_exec += 1
                except AppError as exc:
                    failures.append(f"{q.id}: {exc.message}")
            else:
                failures.append(f"{q.id}: {v.error_summary}")
        return {"queries": total, "valid": ok_valid, "executed": ok_exec, "failures": failures}

    def _generate_with_retry(self, question: str):
        """Generate with patience for provider hiccups, so a busy API does not turn into wrong scores.

        Rate limits wait 10, 20, 40, 60, 60, 60 seconds. Overloads, timeouts and intermittent "model not found" answers
        (seen from Gemini under load) are retried once after 30 seconds, because on a free key every failed request also uses quota. Two such questions in a row stop the run. Anything else fails the question immediately.
        """
        if self._model_blocked:
            raise LLMRateLimitError("Skipped: the model was unavailable or out of quota earlier in this run.")
        rate_delay, transient_tries = 10.0, 0
        transient_delays = (30.0,)  # every attempt costs quota on a free key, so retry once, not endlessly
        rate_tries = 0
        while True:
            try:
                out = self.qs.generate(question, record=False)
                self._rate_limited_questions = self._overloaded_questions = 0
                return out
            except LLMQuotaExhaustedError:
                self._model_blocked = True
                logger.warning("daily model quota is used up; skipping the model for the rest of this run")
                raise
            except LLMRateLimitError:
                if rate_tries >= self.rate_limit_retries:
                    self._rate_limited_questions += 1
                    if self._rate_limited_questions >= 2:
                        # two questions in a row stayed limited after minutes of waiting: this is a quota, not a burst
                        self._model_blocked = True
                        logger.warning("model quota looks exhausted; skipping the model for the rest of this run")
                    raise
                rate_tries += 1
                logger.info("rate limited; waiting %.0fs", rate_delay)
                self._sleep(rate_delay)
                rate_delay = min(rate_delay * 2, 60.0)
            except (LLMOverloadedError, LLMModelNotFoundError, LLMTimeoutError):
                if transient_tries >= len(transient_delays):
                    self._overloaded_questions += 1
                    if self._overloaded_questions >= 2:
                        # the provider is down for now: stop spending quota on requests that fail
                        self._model_blocked = True
                        logger.warning("provider keeps failing; skipping the model for the rest of this run")
                    raise
                self._sleep(transient_delays[transient_tries])
                transient_tries += 1

    def _run_question(self, q: EvalQuestion, dataset: EvalDataset, mode: str) -> QuestionResult:
        res = QuestionResult(id=q.id, category=q.category, question=q.question, expected_behavior=q.expected_behavior)
        try:
            if mode == "retrieval_only":
                r = self.qs.retriever.retrieve(q.question)
                res.retrieval_ms = r.latency_ms
                res.semantic_tables = [t.name for t in r.semantic_tables]
                res.retrieved_tables = r.table_names
            else:
                out = self._generate_with_retry(q.question)
                res.status = out.status
                res.llm_model = self.settings.llm_model
                res.generated_sql = out.sql
                res.sql_valid = bool(out.validation and out.validation.valid) if out.status in ("ok", "invalid_sql") else None
                res.generation_ms = out.latency.total_ms
                res.retrieval_ms = out.latency.retrieval_ms
                res.attempts = out.attempts
                res.assumptions = out.assumptions
                res.semantic_tables = [t.name for t in out.retrieval.semantic_tables] if out.retrieval else []
                res.retrieved_tables = [t.name for t in out.retrieval.tables] if out.retrieval else []
                self._score_generation(q, out, res)
        except AppError as exc:
            res.status, res.error = "error", exc.message
        except Exception:
            logger.exception("evaluation question failed", extra={"question_id": q.id})
            res.status, res.error = "error", "Unexpected error while evaluating this question."

        if res.status == "error" and not res.semantic_tables:
            # retrieval needs no LLM, so measure it even when generation failed
            try:
                r = self.qs.retriever.retrieve(q.question)
                res.retrieval_ms = r.latency_ms
                res.semantic_tables = [t.name for t in r.semantic_tables]
                res.retrieved_tables = r.table_names
            except Exception:
                logger.warning("retrieval fallback failed", extra={"question_id": q.id})

        res.recall_at_k, res.precision_at_k = _prf(q.expected_tables, res.semantic_tables)
        res.recall_expanded, res.precision_expanded = _prf(q.expected_tables, res.retrieved_tables)
        return res

    def _score_generation(self, q: EvalQuestion, out, res: QuestionResult) -> None:
        if q.expected_behavior == "refuse":
            res.behavior_ok = out.status != "ok"
            return
        if q.expected_behavior == "clarify_or_assume":
            res.behavior_ok = out.status == "clarification_needed" or (out.status == "ok" and bool(out.assumptions))
            if out.status != "ok":
                return
        elif out.status != "ok":
            return
        # the model produced a valid query: run it
        try:
            actual = self.executor.execute(out.sql, max_rows=self.settings.max_result_rows)
            res.executed = True
            res.execution_ms = actual.execution_time_ms
        except AppError as exc:
            res.executed, res.error = False, exc.message
            return
        if q.expected_sql:
            res.exact_sql_match = _norm_sql(out.sql, self.validator) == _norm_sql(q.expected_sql, self.validator)
            if q.scoring == "result":
                expected = self.executor.execute(q.expected_sql, max_rows=self.settings.max_result_rows)
                res.execution_match = results_match(expected.rows, actual.rows, q.ordered)
                res.execution_match_extra_columns = res.execution_match or results_match_allowing_extra_columns(
                    expected.rows, actual.rows, q.ordered
                )

    def _run_adversarial(self, dataset: EvalDataset) -> list[AdversarialResult]:
        schema = self.schema_service.get_schema()
        out: list[AdversarialResult] = []
        for case in dataset.adversarial_sql:
            v = self.validator.validate(case.sql, schema)
            blocked = False
            try:
                self.executor.execute(case.sql)
            except AppError:
                blocked = True
            out.append(
                AdversarialResult(
                    id=case.id, sql=case.sql, why=case.why, rejected_by_validator=not v.valid,
                    blocked_end_to_end=blocked, rule=v.errors[0].code if v.errors else None,
                )
            )
        return out

    # -- aggregation ----------------------------------------------------------------------
    def _build_report(self, mode, dataset, results, adversarial, golden, started, fingerprint) -> EvalReport:
        s = self.settings
        answer_qs = {q.id: q for q in dataset.questions if q.expected_behavior == "answer"}
        errors = [r for r in results if r.status == "error"]
        # questions that hit a provider error were never answered; they are reported, not scored as wrong
        done = [r for r in results if r.status != "error"]
        ans = [r for r in done if r.id in answer_qs]
        refuse = [r for r in done if r.expected_behavior == "refuse"]
        clarify = [r for r in done if r.expected_behavior == "clarify_or_assume"]
        strict = [r for r in ans if answer_qs[r.id].scoring == "result" and answer_qs[r.id].expected_sql]

        metrics: dict[str, Any] = {
            "questions_total": len(results),
            "questions_evaluated": len(done),
            "questions_answerable": len(ans),
            "questions_strict_scored": len(strict),
            "adversarial_cases": len(adversarial),
        }
        # retrieval (needs no LLM)
        with_tables = [r for r in results if r.recall_at_k is not None]
        metrics["retrieval_questions_scored"] = len(with_tables)
        metrics["recall_at_k_semantic"] = _mean([r.recall_at_k for r in with_tables])
        metrics["precision_at_k_semantic"] = _mean([r.precision_at_k for r in with_tables])
        metrics["recall_after_expansion"] = _mean([r.recall_expanded for r in with_tables])
        metrics["precision_after_expansion"] = _mean([r.precision_expanded for r in with_tables])
        metrics["avg_retrieval_ms"] = _mean([r.retrieval_ms for r in results])
        # validator / safety (needs no LLM)
        metrics["invalid_query_rejection_rate_validator"] = _rate(sum(a.rejected_by_validator for a in adversarial), len(adversarial))
        metrics["invalid_query_blocked_end_to_end"] = _rate(sum(a.blocked_end_to_end for a in adversarial), len(adversarial))
        metrics["golden_sql_valid_rate"] = _rate(golden["valid"], golden["queries"])
        metrics["golden_sql_execution_rate"] = _rate(golden["executed"], golden["queries"])

        if mode == "full":
            generated = [r for r in ans if r.status in ("ok", "invalid_sql")]
            metrics["sql_validity_rate"] = _rate(sum(1 for r in ans if r.sql_valid), len(ans))
            metrics["execution_success_rate"] = _rate(sum(1 for r in ans if r.executed), len(ans))
            metrics["execution_accuracy"] = _rate(sum(1 for r in strict if r.execution_match), len(strict))
            metrics["execution_accuracy_extra_columns_allowed"] = _rate(sum(1 for r in strict if r.execution_match_extra_columns), len(strict))
            metrics["exact_sql_match_rate"] = _rate(sum(1 for r in strict if r.exact_sql_match), len(strict))
            metrics["refusal_correct_rate"] = _rate(sum(1 for r in refuse if r.behavior_ok), len(refuse))
            metrics["ambiguity_handled_rate"] = _rate(sum(1 for r in clarify if r.behavior_ok), len(clarify))
            metrics["avg_generation_latency_ms"] = _mean([r.generation_ms for r in done if r.status is not None])
            metrics["avg_execution_ms"] = _mean([r.execution_ms for r in results])
            metrics["questions_with_errors"] = len(errors)
            metrics["successful_generations"] = sum(1 for r in ans if r.status == "ok")
            _ = generated
            unsafe = len(refuse) + len(adversarial)
            ok = sum(1 for r in refuse if r.behavior_ok) + sum(1 for a in adversarial if a.blocked_end_to_end)
            metrics["invalid_query_rejection_rate_overall"] = _rate(ok, unsafe)

        by_cat: dict[str, dict[str, Any]] = {}
        groups: dict[str, list[QuestionResult]] = defaultdict(list)
        for r in results:
            groups[r.category].append(r)
        for cat, rs in sorted(groups.items()):
            entry: dict[str, Any] = {"questions": len(rs)}
            if mode == "full":
                entry["errors"] = sum(1 for r in rs if r.status == "error")
                sc = [r for r in rs if r.execution_match is not None]
                entry["execution_accuracy"] = _rate(sum(1 for r in sc if r.execution_match), len(sc))
                entry["valid_sql"] = sum(1 for r in rs if r.sql_valid)
                entry["behavior_ok"] = sum(1 for r in rs if r.behavior_ok)
            by_cat[cat] = entry

        notes = []
        if mode == "retrieval_only":
            notes.append("LLM was not configured: only retrieval, validator and dataset checks were measured. LLM-dependent metrics are intentionally absent.")
        if s.embedding_provider == "hashing":
            notes.append("Embeddings came from the offline hashing embedder, not Sentence Transformers; retrieval numbers do not describe all-MiniLM-L6-v2.")
        if self._model_blocked and self._overloaded_questions >= 2:
            notes.append(
                "The provider kept answering 'overloaded', 'unavailable' or timing out, so the model was skipped for the rest of the run to "
                "avoid wasting request quota. Run Resume again later."
            )
        elif self._model_blocked:
            notes.append(
                "The provider kept answering 'rate limit reached' even after long waits, so the model was skipped for the rest "
                "of the run. This usually means the daily quota of the API key is used up. Wait for the quota to reset, use a "
                "key or plan with a higher quota, or choose another model with LLM_MODEL."
            )
        if errors:
            notes.append(
                f"{len(errors)} of {len(results)} questions could not be evaluated because of provider errors "
                "(rate limits, overloads or model availability) and are excluded from the rates above. "
                "The evaluation is incomplete; run it again to cover them."
            )
        if golden["failures"]:
            notes.append(f"{len(golden['failures'])} golden query(ies) failed their own sanity check; see golden_sql_check.")
        return EvalReport(
            run_id=started.strftime("%Y%m%dT%H%M%SZ"), mode=mode, started_at=started, finished_at=datetime.now(timezone.utc),
            llm_provider=s.llm_provider if mode == "full" else None, llm_model=s.llm_model if mode == "full" else None,
            embedding_provider=s.embedding_provider, embedding_model=self.qs.retriever.embedder.model_name,
            retrieval_top_k=s.retrieval_top_k, retrieval_max_tables=s.retrieval_max_tables, schema_fingerprint=fingerprint,
            dataset_version=dataset.version, metrics=metrics, by_category=by_cat, results=results, adversarial=adversarial,
            golden_sql_check=golden, notes=notes,
        )

    def _persist(self, report: EvalReport) -> None:
        d = self.settings.evaluation_reports_dir
        d.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump_json(indent=2)
        (d / "latest.json").write_text(payload)
        (d / f"report_{report.run_id}.json").write_text(payload)
        (d / "latest.md").write_text(render_markdown(report))


def _pct(x) -> str:
    return "n/a (not measured)" if x is None else f"{x * 100:.1f}%"


def _ms(x) -> str:
    return "n/a (not measured)" if x is None else f"{x:,.0f} ms"


def render_markdown(r: EvalReport) -> str:
    m = r.metrics
    lines = [
        f"# QueryMind AI evaluation report",
        "",
        f"- Run: `{r.run_id}` | mode: **{r.mode}**",
        f"- LLM: {r.llm_provider or 'not used'} / {r.llm_model or '-'}",
        f"- Embeddings: {r.embedding_provider} / {r.embedding_model} | top-k documents: {r.retrieval_top_k} | max tables: {r.retrieval_max_tables}",
        f"- Dataset version {r.dataset_version}: {m['questions_total']} questions ({m['questions_answerable']} answerable, {m['questions_strict_scored']} scored on results) and {m['adversarial_cases']} adversarial SQL cases",
        f"- Schema fingerprint: `{r.schema_fingerprint}`",
        "",
        "All numbers below were measured in this run. Metrics shown as n/a were not measured.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| SQL validity rate | {_pct(m.get('sql_validity_rate'))} |",
        f"| Execution success rate | {_pct(m.get('execution_success_rate'))} |",
        f"| Execution accuracy (result match) | {_pct(m.get('execution_accuracy'))} |",
        f"| Execution accuracy, extra columns allowed | {_pct(m.get('execution_accuracy_extra_columns_allowed'))} |",
        f"| Exact SQL match | {_pct(m.get('exact_sql_match_rate'))} |",
        f"| Schema retrieval Recall@K (semantic tables) | {_pct(m.get('recall_at_k_semantic'))} |",
        f"| Schema retrieval Precision@K (semantic tables) | {_pct(m.get('precision_at_k_semantic'))} |",
        f"| Recall after FK expansion | {_pct(m.get('recall_after_expansion'))} |",
        f"| Precision after FK expansion | {_pct(m.get('precision_after_expansion'))} |",
        f"| Avg generation latency | {_ms(m.get('avg_generation_latency_ms'))} |",
        f"| Avg query execution time | {_ms(m.get('avg_execution_ms'))} |",
        f"| Adversarial SQL rejected by validator | {_pct(m.get('invalid_query_rejection_rate_validator'))} |",
        f"| Adversarial SQL blocked end to end | {_pct(m.get('invalid_query_blocked_end_to_end'))} |",
        f"| Refusal correct (nonexistent / out-of-scope / unsafe) | {_pct(m.get('refusal_correct_rate'))} |",
        f"| Ambiguity handled (clarify or state assumption) | {_pct(m.get('ambiguity_handled_rate'))} |",
        f"| Golden SQL valid / executes | {_pct(m.get('golden_sql_valid_rate'))} / {_pct(m.get('golden_sql_execution_rate'))} |",
        "",
    ]
    if r.notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in r.notes] + [""]
    lines += ["## By category", "", "| Category | Questions | Execution accuracy | Valid SQL | Behavior ok |", "|---|---|---|---|---|"]
    for cat, e in r.by_category.items():
        lines.append(f"| {cat} | {e['questions']} | {_pct(e.get('execution_accuracy'))} | {e.get('valid_sql', 'n/a')} | {e.get('behavior_ok', 'n/a')} |")
    lines += ["", "## Per question", "", "| ID | Category | Status | Valid | Executed | Result match | Recall@K | Precision@K | Gen ms |", "|---|---|---|---|---|---|---|---|---|"]
    def f(x):
        return "-" if x is None else ("yes" if x is True else "no" if x is False else f"{x:.2f}" if isinstance(x, float) else str(x))
    for x in r.results:
        lines.append(f"| {x.id} | {x.category} | {x.status or '-'} | {f(x.sql_valid)} | {f(x.executed)} | {f(x.execution_match)} | {f(x.recall_at_k)} | {f(x.precision_at_k)} | {f(x.generation_ms)} |")
    failed = [x for x in r.results if x.execution_match is False or x.error]
    if failed:
        lines += ["", "## Failures", ""]
        for x in failed:
            lines += [f"### {x.id}: {x.question}", "", f"- status: {x.status}; error: {x.error or '-'}", "", "```sql", x.generated_sql or "-- no SQL", "```", ""]
    lines += ["", "## Adversarial SQL", "", "| ID | Rule | Rejected | Blocked end to end | Why |", "|---|---|---|---|---|"]
    for a in r.adversarial:
        lines.append(f"| {a.id} | {a.rule or '-'} | {'yes' if a.rejected_by_validator else 'NO'} | {'yes' if a.blocked_end_to_end else 'NO'} | {a.why} |")
    if r.golden_sql_check["failures"]:
        lines += ["", "## Golden SQL failures", ""] + [f"- {x}" for x in r.golden_sql_check["failures"]]
    return "\n".join(lines) + "\n"
