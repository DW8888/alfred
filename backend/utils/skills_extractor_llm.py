# backend/utils/skills_extractor_llm.py
import os
import json
from typing import Dict, List, Any
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_INSTRUCTIONS = """
You are a strict information extraction engine.

Task:
- Extract technical skills from the provided text.
- Return ONLY valid JSON, no comments, no extra keys.

Output JSON schema:
{
  "languages": [string, ...],
  "cloud": [string, ...],
  "data_eng": [string, ...],
  "analytics": [string, ...],
  "ml_ai": [string, ...],
  "devops": [string, ...],
  "security": [string, ...],
  "tools": [string, ...],
  "certs": [string, ...],
  "all": [string, ...]
}

Categories:
- languages: programming languages (e.g., python, java, r, sql, c#, c++, javascript)
- cloud: cloud providers + cloud services (e.g., aws, azure, gcp, bedrock, sagemaker)
- data_eng: etl/elt, pipelines, airflow, dbt, spark, kafka, warehousing, sql, nosql, data lakes, data bases, db,mysql, postgres, mongodb,dynamodb,redshift
- analytics: statistics, bi tools, data viz (e.g., tableau, power bi, matplotlib)
- ml_ai: ml/dl algorithms, frameworks, llms, rag, embeddings, transformers, tensorflow, pytorch, scikit-learnm, keras, huggingface, openai api, langchain,llama 
- devops: ci/cd, docker, kubernetes, terraform, gitops
- security: iam, encryption, soc, siem, ids/ips, security frameworks, cia, nist, gdpr, hipaa, compliance, log, log monitoring, dashboards
- tools: general tooling (git, linux, vs code, jupyter, etc.)
- certs: professional certifications (e.g., aws certified solutions architect – associate), compTIA security+, cissp, pmp,cissp,azure fundamentals

Normalization rules:
- All strings MUST be lowercase.
- Trim whitespace.
- Deduplicate any repeated skills.
- The "all" list MUST be the deduplicated union of all other category lists.
- If a category has no skills, return an empty list for that category.

Constraints:
- Only include skills explicitly supported by the text.
- Do NOT invent skills or certifications.
- MUST return syntactically valid JSON that can be parsed with a standard JSON parser.
"""

def _build_all_union(raw: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Ensure:
    - all keys exist
    - everything is lowercase
    - 'all' is the union of the other categories
    """
    categories = [
        "languages", "cloud", "data_eng", "analytics",
        "ml_ai", "devops", "security", "tools", "certs"
    ]
    cleaned: Dict[str, List[str]] = {}
    union_set = set()

    for cat in categories:
        vals = raw.get(cat, []) or []
        norm_vals = sorted({str(v).strip().lower() for v in vals if str(v).strip()})
        cleaned[cat] = norm_vals
        union_set |= set(norm_vals)

    # handle 'all'
    all_vals = raw.get("all", [])
    all_norm = {str(v).strip().lower() for v in (all_vals or []) if str(v).strip()}
    union_set |= all_norm

    cleaned["all"] = sorted(union_set)
    return cleaned


def extract_skills_llm(text: str) -> Dict[str, List[str]]:
    """
    Extract structured skill lists using GPT-4o-mini.

    Returns a dict:
      {
        "languages": [...],
        "cloud": [...],
        ...
        "all": [...]
      }

    If anything goes wrong, returns all-empty lists.
    """
    text = (text or "").strip()
    if not text:
        return {
            "languages": [],
            "cloud": [],
            "data_eng": [],
            "analytics": [],
            "ml_ai": [],
            "devops": [],
            "security": [],
            "tools": [],
            "certs": [],
            "all": [],
        }

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": f"Extract technical skills from this text:\n\n{text}"},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = completion.choices[0].message.content

        if isinstance(content, str):
            raw = json.loads(content)
        elif isinstance(content, dict):
            raw = content
        else:
            raw = {}

        cleaned = _build_all_union(raw)

        # Debug hook
        # print("\n================ DEBUG: RAW LLM SKILLS (NORMALIZED) ================\n")
        # print(json.dumps(cleaned, indent=2))
        # print("\n=================================================================\n")

        return cleaned

    except Exception as e:
        # print("!!! extract_skills_llm FAILED !!!", repr(e))
        return {
            "languages": [],
            "cloud": [],
            "data_eng": [],
            "analytics": [],
            "ml_ai": [],
            "devops": [],
            "security": [],
            "tools": [],
            "certs": [],
            "all": [],
        }
