import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv
from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import GeneratedArtifact, Job, PromptExperiment  # noqa: E402
from backend.routes.jobs import _build_context  # noqa: E402
from backend.utils.embedding import embed_text  # noqa: E402
from sqlalchemy import text  # noqa: E402


def build_variant_filter(variants: Optional[List[str]]) -> Optional[List[str]]:
    """Normalize optional resume variant names (P0 -> resume_P0)."""
    if not variants:
        return None
    normalized: List[str] = []
    for name in variants:
        name = name.strip()
        if not name:
            continue
        normalized.append(name if name.startswith("resume") else f"resume_{name}")
    return normalized or None


def fetch_resume_artifacts(
    session,
    start_id: int,
    limit: Optional[int],
    variants: Optional[List[str]],
    job_ids: Optional[List[int]],
) -> List[GeneratedArtifact]:
    """Return resume artifacts beginning at `start_id`, ordered ascending."""
    query = (
        session.query(GeneratedArtifact)
        .filter(GeneratedArtifact.artifact_type.ilike("resume%"))
        .filter(GeneratedArtifact.id >= start_id)
        .order_by(GeneratedArtifact.id.asc())
    )
    if variants:
        query = query.filter(GeneratedArtifact.artifact_type.in_(variants))
    if job_ids:
        query = query.filter(GeneratedArtifact.job_id.in_(job_ids))
    if limit:
        query = query.limit(limit)
    return query.all()


def build_context(session, job: Job, top_k: int) -> str:
    """Rehydrate the retrieval context for the supplied job."""
    job_text = f"{job.title or ''}\n{job.company or ''}\n{job.description or ''}"
    embedding = job.description_embedding if job.description_embedding is not None else embed_text(job_text)

    sql = text(
        """
        SELECT name, content,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM artifacts
        ORDER BY similarity DESC
        LIMIT :top_k;
        """
    )
    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()
    rows = session.execute(sql, {"embedding": embedding, "top_k": top_k}).fetchall()
    context, _ = _build_context(rows)
    return context[:8000]


def build_test_case(job: Job, resume_text: str, context: str) -> LLMTestCase:
    """Wrap a job + resume into the Deepeval structure."""
    job_text = f"{job.title or ''}\n{job.company or ''}\n{job.description or ''}"
    return LLMTestCase(
        input=job_text,
        actual_output=resume_text,
        retrieval_context=[context],
        additional_metadata={},
    )


def score_artifacts(artifacts: Iterable[GeneratedArtifact], top_k: int) -> List[dict]:
    """Compute automated scores for every resume artifact."""
    session = SessionLocal()
    outputs: List[dict] = []

    punctuality_metric = FaithfulnessMetric(
        threshold=0.8,
        model="gpt-5-mini",
        include_reason=True,
    )
    tone_metric = GEval(
        name="Tone and Persona",
        criteria=(
            "Evaluate the tone of the resume:\n"
            "- Professionalism (1-5)\n"
            "- Action-Oriented (1-5)\n"
            "- Persona Alignment (1-5)\n"
            "Return the average score."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model="gpt-5-mini",
    )
    alignment_metric = GEval(
        name="Alignment",
        criteria=(
            "Score 1-10 based on how well the resume aligns with the job description (INPUT).\n"
            "- The resume should reference responsibilities, tools, and outcomes required in the job.\n"
            "- Penalize generic resumes that ignore the specific company/title."
        ),
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model="gpt-5-mini",
    )
    impact_metric = GEval(
        name="Impact",
        criteria=(
            "Score 1-10 for action-oriented writing with measurable results.\n"
            "- Each bullet should highlight an accomplishment, metric, or business outcome.\n"
            "- Penalize passive language or vague descriptions."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model="gpt-5-mini",
    )
    credtail_metric = GEval(
        name="CredTail",
        criteria=(
            "Score 1-10 for credible Education/Experience/Core Skills relative to the retrieval context.\n"
            "- Ensure degrees, employers, dates, and core technologies appear in the verified context.\n"
            "- Penalize fabricated or missing details."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        model="gpt-5-mini",
    )

    for artifact in artifacts:
        job = session.get(Job, artifact.job_id)
        if not job:
            print(f"[SKIP] Artifact {artifact.id} has no job reference.")
            continue

        context = build_context(session, job, top_k)
        test_case = build_test_case(job, artifact.content, context)

        punctuality_metric.measure(test_case)
        tone_metric.measure(test_case)
        alignment_metric.measure(test_case)
        impact_metric.measure(test_case)
        credtail_metric.measure(test_case)

        punctuality_score = punctuality_metric.score * 10
        tone_score = tone_metric.score * 10
        alignment_score = alignment_metric.score * 10
        impact_score = impact_metric.score * 10
        credtail_score = credtail_metric.score * 10
        total_score = punctuality_score + tone_score + alignment_score + impact_score + credtail_score

        variant_name = "P0"
        if "_" in artifact.artifact_type:
            variant_name = artifact.artifact_type.split("_", 1)[1] or "P0"

        outputs.append(
            {
                "job_id": job.id,
                "job_title": job.title,
                "artifact_id": artifact.id,
                "variant": variant_name,
                "punctuality_score": punctuality_metric.score,
                "punctuality_reason": punctuality_metric.reason,
                "tone_score": tone_metric.score,
                "tone_reason": tone_metric.reason,
                "alignment_score": alignment_metric.score,
                "alignment_reason": alignment_metric.reason,
                "impact_score": impact_metric.score,
                "impact_reason": impact_metric.reason,
                "credtail_score": credtail_metric.score,
                "credtail_reason": credtail_metric.reason,
            }
        )

        experiment = (
            session.query(PromptExperiment)
            .filter(
                PromptExperiment.job_id == job.id,
                PromptExperiment.variant_name == variant_name,
            )
            .first()
        )
        if not experiment:
            experiment = PromptExperiment(
                job_id=job.id,
                variant_name=variant_name,
                generated_artifact_id=artifact.id,
            )
            session.add(experiment)

        experiment.punctuality_score = punctuality_score
        experiment.tone_score = tone_score
        experiment.alignment_score = alignment_score
        experiment.impact_score = impact_score
        experiment.credtail_score = credtail_score
        experiment.total_score = total_score
        experiment.judge_reasoning = (
            "Punctuality: "
            f"{punctuality_metric.reason}\nTone: {tone_metric.reason}\nAlignment: {alignment_metric.reason}\n"
            f"Impact: {impact_metric.reason}\nCredTail: {credtail_metric.reason}"
        )

        session.commit()
        print(f"[OK] Evaluated artifact {artifact.id} (job {job.id}, variant {variant_name})")

    session.close()
    return outputs


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate resumes starting from a specific artifact ID without queue/state tracking."
    )
    parser.add_argument("--start-id", type=int, required=True, help="Artifact ID to start from (inclusive).")
    parser.add_argument("--limit", type=int, help="Optional cap on number of artifacts to judge.")
    parser.add_argument("--variants", type=str, help="Comma-separated artifact variants (e.g., P0,P1,resume_custom).")
    parser.add_argument("--job-ids", type=str, help="Comma-separated job IDs to restrict evaluation to.")
    parser.add_argument("--top-k", type=int, default=5, help="Artifacts to retrieve when rebuilding context.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model/experimentation/outputs"),
        help="Directory to write Deepeval output JSON.",
    )
    args = parser.parse_args()

    load_dotenv()
    os.environ.setdefault("OPENAI_COST_PER_INPUT_TOKEN", "0.00000125")
    os.environ.setdefault("OPENAI_COST_PER_OUTPUT_TOKEN", "0.000004")

    job_ids = [int(x) for x in args.job_ids.split(",")] if args.job_ids else None
    variant_filter = build_variant_filter(
        [chunk.strip() for chunk in args.variants.split(",")] if args.variants else None
    )

    session = SessionLocal()
    try:
        artifacts = fetch_resume_artifacts(session, args.start_id, args.limit, variant_filter, job_ids)
    finally:
        session.close()

    if not artifacts:
        print("No resume artifacts matched the requested filters.")
        return

    outputs = score_artifacts(artifacts, args.top_k)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / f"deepeval_resume_from_id_{timestamp}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(outputs, fh, indent=2)

    print(f"Wrote {len(outputs)} evaluations to {out_path}")


if __name__ == "__main__":
    main()
