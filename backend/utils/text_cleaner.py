import re

def clean_text(text: str) -> str:
    """Cleans raw text input for safe embedding and model processing."""
    if not text:
        return ""

    # Replace control characters, carriage returns, tabs, and excessive whitespace
    text = re.sub(r"[\r\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = text.strip()
    return text
