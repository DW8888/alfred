from fastapi import APIRouter, HTTPException
from openai import OpenAI
import os

router = APIRouter(
    prefix="/generate",
    tags=["Generate"]
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@router.post("/github_summary")
def generate_github_summary(payload: dict):
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a summarization engine that produces structured GitHub project summaries. "
                        "Your output must be concise, factual, and formatted for ingestion into a job application assistant."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        summary_text = resp.choices[0].message.content
        return {"summary_text": summary_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  