import sys, os, base64, glob
from openai import OpenAI
from sqlalchemy.orm import Session
from backend.db.repo import SessionLocal
from backend.db.models import Artifact
from dotenv import load_dotenv
from docx import Document
from PyPDF2 import PdfReader
from bs4 import BeautifulSoup

# ------------------------------------------------------
# Environment setup
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------
# 1. Text cleaning utility
# ------------------------------------------------------
def clean_text_for_db(text: str) -> str:
    """Remove null bytes and invisible control characters before DB insert."""
    if not text:
        return ""
    # Remove NULL bytes and low-ASCII control characters
    cleaned = text.replace("\x00", "")
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32 or ch in ("\n", "\t"))
    return cleaned.strip()

# ------------------------------------------------------
# 2. Embedding generator
# ------------------------------------------------------
def embed_text(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

# ------------------------------------------------------
# 3. File extraction functions
# ------------------------------------------------------
def extract_text_from_docx(file_path):
    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    return clean_text_for_db(text)

def extract_text_from_pdf(file_path):
    from PyPDF2.errors import DependencyError
    text = ""
    try:
        reader = PdfReader(file_path)
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
    except DependencyError:
        print(f"⚠️ Skipping encrypted PDF (requires decryption): {file_path}")
    return clean_text_for_db(text)

def extract_text_from_html(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, "html.parser")
    return clean_text_for_db(soup.get_text(separator="\n", strip=True))

def extract_text_from_image(file_path):
    with open(file_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an assistant describing technical diagrams."},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": f"data:image/png;base64,{img_data}"}],
            },
        ],
    )
    return clean_text_for_db(response.choices[0].message.content)

# ------------------------------------------------------
# 4. Generic loader to pick the right extraction
# ------------------------------------------------------
def load_file_content(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return clean_text_for_db(f.read())
    elif ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    elif ext in [".html", ".htm"]:
        return extract_text_from_html(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        return extract_text_from_image(file_path)
    else:
        print(f"Unsupported file type: {ext}")
        return None

# ------------------------------------------------------
# 5. Database ingestion
# ------------------------------------------------------
def ingest_document(name: str, content: str, source: str, hash_value: str | None = None):
    db: Session = SessionLocal()
    content = clean_text_for_db(content)
    embedding = embed_text(content)
    artifact = Artifact(name=name, content=content, embedding=embedding, source=source)
    db.add(artifact)
    db.commit()
    db.close()
    print(f"✅ Ingested {name} from {source}")

# ------------------------------------------------------
# 6. Dynamic entry point
# ------------------------------------------------------
if __name__ == "__main__":
    data_dir = "backend/knowledge_base/data"
    supported_ext = (".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".png", ".jpg", ".jpeg")

    files = [f for f in glob.glob(os.path.join(data_dir, "*")) if os.path.splitext(f)[1].lower() in supported_ext]

    if not files:
        print(f"No supported files found in {data_dir}")
    else:
        print(f"Found {len(files)} supported files:")
        for file_path in files:
            name = os.path.basename(file_path)
            print(f"→ Processing {name}")
            content = load_file_content(file_path)
            if content:
                ingest_document(name, content, "Auto")
