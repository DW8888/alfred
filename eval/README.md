# Eval

Artifacts and datasets used to manually/automatically evaluate Alfred’s outputs.

## Contents

- `sets/` – grouped evaluation prompts/data for larger experimentation.
- `job_<id>_reasoning.txt` – reasoning traces captured during resume generation for the specified job posting, useful for auditing LLM thought processes.
- `job_<id>_resume.md` – markdown resumes generated for each test job; paired with the reasoning files.
- `resume_eval_data.json` – structured summary of evaluation results (scores, metadata, reviewer feedback).
