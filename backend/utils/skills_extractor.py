import re
from typing import Dict, List, Set


# Very lightweight, extensible keyword-based skill extractor.
# This is "Option B foundation": we can later plug in an LLM
# to refine this output, but we don't have to change the interface.


SKILL_DICTIONARIES: Dict[str, List[str]] = {
    "languages": [
        "python", "r", "java", "javascript", "typescript", "scala",
        "sql", "bash", "shell", "c++", "c#", "go", "rust"
    ],
    "cloud": [
        "aws", "amazon web services", "azure", "gcp", "google cloud",
        "lambda", "s3", "ec2", "glue", "athena", "redshift", "emr",
        "bedrock", "sagemaker"
    ],
    "data_eng": [
        "airflow", "dbt", "spark", "pyspark", "kafka", "flink",
        "etl", "elt", "data pipeline", "data warehousing", "snowflake",
        "databricks", "bigquery"
    ],
    "ml_ai": [
        "machine learning", "deep learning", "neural network",
        "gradient boosting", "xgboost", "random forest",
        "logistic regression", "linear regression",
        "pytorch", "tensorflow", "keras", "scikit-learn",
        "llm", "rag", "retrieval augmented generation", "embeddings",
        "nlp", "natural language processing"
    ],
    "databases": [
        "postgres", "postgresql", "mysql", "sql server", "oracle",
        "mongo", "mongodb", "redis", "snowflake", "redshift"
    ],
    "tools": [
        "git", "github", "docker", "kubernetes", "terraform",
        "ansible", "linux", "unix", "jenkins", "ci/cd"
    ],
    "analytics": [
        "pandas", "numpy", "matplotlib", "seaborn", "tableau",
        "power bi", "looker", "excel", "statistics"
    ],
    "security": [
        "cybersecurity", "iam", "identity and access management",
        "encryption", "zero trust", "siem", "soc", "nmap", "wireshark"
    ],
    "certs": [
        "aws certified solutions architect", "aws csa",
        "aws certified cloud practitioner", "aws ccp",
        "aws certified ai practitioner",
        "google cybersecurity certificate", "security+",
        "ccsp", "cissp"
    ],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_skills(text: str) -> Dict[str, List[str]]:
    """
    Lightweight, deterministic skill extractor.
    Returns:
      {
        "languages": [...],
        "cloud": [...],
        ...
        "all": [...deduped union...]
      }
    """
    norm = normalize_text(text)
    found: Dict[str, Set[str]] = {}

    for category, keywords in SKILL_DICTIONARIES.items():
        cat_hits: Set[str] = set()
        for kw in keywords:
            # Anchor on word boundaries where possible
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, norm):
                cat_hits.add(kw)
        if cat_hits:
            found[category] = cat_hits

    # Build "all" union
    all_skills: Set[str] = set()
    for s in found.values():
        all_skills |= s

    return {
        **{k: sorted(list(v)) for k, v in found.items()},
        "all": sorted(list(all_skills))
    }


def skill_overlap(job_skills: Dict[str, List[str]], artifact_skills: Dict[str, List[str]]) -> float:
    """
    Compute overlap between two skill dicts using "all".
    Returns Jaccard similarity: |intersection| / |union|
    """
    job_set = set(job_skills.get("all", []))
    art_set = set(artifact_skills.get("all", []))

    if not job_set or not art_set:
        return 0.0

    inter = job_set & art_set
    union = job_set | art_set

    return len(inter) / len(union)
