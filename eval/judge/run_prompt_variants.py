import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from openai import OpenAI

import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import Job, GeneratedArtifact  # noqa: E402
from backend.profile.utils import load_profile  # noqa: E402
from backend.utils.embedding import embed_text  # noqa: E402
from backend.routes.jobs import _persist_generated_artifact  # noqa: E402
from sqlalchemy import text  # noqa: E402

PROMPT_FILES = {
    "P0": "p0_control.txt",
    "P1": "p1_resume_architect.txt",
    "P2": "p2_factual_auditor.txt",
    "P3": "p3_precise_wordsmith.txt",
    "P4": "p4_conservative_specialist.txt",
}

SQL_ARTIFACT_QUERY = text(
    """
    SELECT name, content,
           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
    FROM artifacts
    ORDER BY similarity DESC
    LIMIT :top_k;
    """
)


def load_prompts(prompt_dir: Path) -> Dict[str, str]:
    """Read all prompt templates into memory."""
    prompts: Dict[str, str] = {}
    for variant, filename in PROMPT_FILES.items():
        path = prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file missing: {path}")
        prompts[variant] = path.read_text(encoding="utf-8", errors="ignore")
    return prompts


def render_prompt(template: str, job_text: str, profile_text: str, kb_text: str, contact_instructions: str) -> str:
    """Fill template placeholders with job/profile/context data."""
    rendered = template
    rendered = rendered.replace("$jd", job_text)
    rendered = rendered.replace("$profile", profile_text)
    rendered = rendered.replace("$kb", kb_text)
    rendered = rendered.replace("{contact_instructions}", contact_instructions)
    return rendered


def build_context_components(rows, profile) -> tuple[str, str, str, str]:
    """Assemble the profile, KB text, combined context, and contact instructions."""
    profile_text = json.dumps(profile, indent=2)
    artifact_chunks = [row.content for row in rows if getattr(row, "content", None)]
    kb_text = "\n\n---\n\n".join(artifact_chunks) if artifact_chunks else "None"
    combined_context = (
        "Structured Profile:\n"
        f"{profile_text}\n\n"
        "Artifacts:\n"
        f"{kb_text}"
    )
    personal_info = profile.get("personal_info", {})
    contact = (
        "Use the following contact information exactly as provided. "
        f"Name: {personal_info.get('name', '')}. "
        f"Location: {personal_info.get('location', '')}. "
        f"Email: {personal_info.get('email', '')}. "
        f"Phone: {personal_info.get('phone', '')}. "
        f"Links: {personal_info.get('links', [])}."
    )
    return profile_text, kb_text, combined_context, contact


def existing_variants(session, job_id: int) -> set[str]:
    """Return resume variants already generated for a job."""
    rows = (
        session.query(GeneratedArtifact.artifact_type)
        .filter(
            GeneratedArtifact.job_id == job_id,
            GeneratedArtifact.artifact_type.like("resume_%"),
        )
        .all()
    )
    variants = set()
    for (artifact_type,) in rows:
        if artifact_type.startswith("resume_"):
            variants.add(artifact_type.split("resume_", 1)[1])
    return variants


def generate_for_variant(
    client: OpenAI,
    variant: str,
    prompt_text: str,
    job,
    profile_text: str,
    kb_text: str,
    combined_context: str,
    contact_instructions: str,
    output_dir: Path,
    db_session,
) -> int:
    """Call the LLM for a single variant and persist the resulting artifact."""
    job_text = f"{job.title or ''}\n{job.company or ''}\n{job.description or ''}"
    system_prompt = render_prompt(prompt_text, job_text, profile_text, kb_text, contact_instructions)
    user_prompt = (
        f"Job Description:\n{job_text}\n\n"
        f"Verified Context:\n{combined_context}\n\n"
        "Return JSON with keys:\n"
        "reasoning: explanation of match strength citing evidence from the context.\n"
        "resume_markdown: the final structured resume in Markdown."
    )

    completion = client.chat.completions.create(
        model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    content = completion.choices[0].message.content
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"reasoning": "", "resume_markdown": content.strip()}

    reasoning = (parsed.get("reasoning") or "").strip()
    resume_md = (
        parsed.get("resume_markdown")
        or parsed.get("resume")
        or parsed.get("resume_text")
        or ""
    ).strip()

    if not resume_md:
        raise ValueError("Empty resume output")

    artifact_id = _persist_generated_artifact(
        db_session,
        job.id,
        job.title or "",
        job.company or "",
        f"resume_{variant}",
        resume_md,
    )

    variant_dir = output_dir / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    out_file = variant_dir / f"job_{job.id}.json"
    with out_file.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "job_id": job.id,
                "variant": variant,
                "reasoning": reasoning,
                "resume_markdown": resume_md,
                "artifact_id": artifact_id,
            },
            fh,
            indent=2,
        )

    return artifact_id or -1


def main():
    parser = argparse.ArgumentParser(description="Run resume prompt variants for top-matching jobs.")
    parser.add_argument("--threshold", type=float, default=0.6, help="Minimum job.match_score to include.")
    parser.add_argument("--limit", type=int, default=10, help="Max number of jobs to process.")
    parser.add_argument("--top-k", type=int, default=5, help="Artifacts to retrieve for context.")
    parser.add_argument("--job-ids", type=str, help="Comma-separated list of job IDs to process (overrides threshold).")
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=Path("model/prompts"),
        help="Directory with prompt templates.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model/experimentation/outputs/prompt_runs"),
        help="Directory to store generated resumes.",
    )
    args = parser.parse_args()

    load_dotenv()
    prompts = load_prompts(args.prompts_dir)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    session = SessionLocal()
    job_ids = [int(x.strip()) for x in args.job_ids.split(",")] if args.job_ids else None
    jobs_query = session.query(Job)
    if job_ids:
        jobs_query = jobs_query.filter(Job.id.in_(job_ids)).order_by(Job.id.asc())
    else:
        jobs_query = (
            jobs_query.filter(Job.match_score.isnot(None))
            .filter(Job.match_score >= args.threshold)
            .order_by(Job.match_score.desc())
        )
        if args.limit:
            jobs_query = jobs_query.limit(args.limit)
    jobs: List[Job] = jobs_query.all()

    if not jobs:
        print("No jobs meet the threshold.")
        return

    profile = load_profile()

    for job in jobs:
        job_text = f"{job.title or ''}\n{job.company or ''}\n{job.description or ''}"
        embedding = embed_text(job_text)
        rows = session.execute(SQL_ARTIFACT_QUERY, {"embedding": embedding, "top_k": args.top_k}).fetchall()
        profile_text, kb_text, combined_context, contact_instructions = build_context_components(rows, profile)
        already_done = existing_variants(session, job.id)

        for variant, template in prompts.items():
            if variant in already_done:
                print(f"[SKIP] Job {job.id} already has variant {variant}")
                continue
            try:
                artifact_id = generate_for_variant(
                    client,
                    variant,
                    template,
                    job,
                    profile_text,
                    kb_text,
                    combined_context,
                    contact_instructions,
                    args.output,
                    session,
                )
                print(f"[OK] Job {job.id} variant {variant} -> artifact {artifact_id}")
            except Exception as exc:
                print(f"[ERR] Job {job.id} variant {variant}: {exc}")

    session.close()


if __name__ == "__main__":
    main()
