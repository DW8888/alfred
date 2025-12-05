import argparse
import json
import os
from pathlib import Path
from time import sleep

import requests
from dotenv import load_dotenv

SYSTEM_PROMPT = (
    "You are a professional resume generator. "
    "Analyze the job description and verified context to determine match quality. "
    "Highlight the skills and responsibilities mentioned in the job description, citing evidence "
    "from the verified context (profile + artifacts). "
    "Produce a structured Markdown resume with sections Header, Summary, Job Fit Highlights, "
    "Core Competencies, Professional Experience, Projects, Education, Certifications, Additional Information. "
    "Only include verifiable facts; never invent dates or employers."
)

USER_TEMPLATE = (
    "Job Description:\n{job_text}\n\n"
    "Key Job Skills/Responsibilities:\n{job_skills}\n\n"
    "Verified Context:\n{combined_context}\n\n"
    "Return JSON with keys:\n"
    "reasoning: explain how the candidate matches the job, referencing the job skills.\n"
    "resume_markdown: structured resume that emphasizes the job's required skills."
)


def fetch_job(api_base: str, job_id: int, retries: int = 3) -> dict:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(f"{api_base}/jobs/{job_id}", timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries:
                raise
            sleep(2 * attempt)


def generate_resume(api_base: str, job: dict, top_k: int, retries: int = 3) -> dict:
    payload = {
        "title": job.get("title", ""),
        "company": job.get("company", "") or "",
        "description": job.get("description", "") or "",
        "top_k": top_k,
        "job_focused": True,
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{api_base}/jobs/generate_resume_job_focus",
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries:
                raise
            sleep(2 * attempt)


def main(job_ids, top_k: int):
    load_dotenv()
    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    eval_dir = Path("eval/job_focus")
    eval_dir.mkdir(parents=True, exist_ok=True)

    samples = []
    for job_id in job_ids:
        job = fetch_job(api_base, job_id)
        resume = generate_resume(api_base, job, top_k)
        resume_md = resume.get("generated_resume", "")
        reasoning = resume.get("reasoning", "")

        (eval_dir / f"job_{job_id}_resume.md").write_text(resume_md, encoding="utf-8")
        (eval_dir / f"job_{job_id}_reasoning.txt").write_text(reasoning, encoding="utf-8")

        samples.append(
            {
                "job_id": job_id,
                "job_title": job.get("title"),
                "company": job.get("company"),
                "job_description": job.get("description") or "",
                "reasoning": reasoning,
                "generated_resume": resume_md,
            }
        )

    dataset = {
        "model_version": "gpt-4o-mini",
        "resume_prompt_system": SYSTEM_PROMPT,
        "resume_prompt_user_template": USER_TEMPLATE,
        "samples": samples,
    }
    (eval_dir / "resume_eval_data.json").write_text(
        json.dumps(dataset, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(samples)} job-focused resumes. Files saved to {eval_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate job-focused resumes for specific job IDs via the backend API."
    )
    parser.add_argument("job_ids", nargs="+", type=int, help="Job IDs to generate resumes for.")
    parser.add_argument("--top-k", type=int, default=5, help="Artifacts to retrieve per job.")
    args = parser.parse_args()
    main(args.job_ids, args.top_k)
