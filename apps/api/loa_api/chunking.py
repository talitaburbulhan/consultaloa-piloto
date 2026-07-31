import hashlib
import json
import math
import re
import unicodedata
from collections import Counter


EMBEDDING_MODEL = "deterministic-token-hash-v1"
EMBEDDING_DIMENSIONS = 256


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


def split_chunks(text: str, target_chars: int = 1200) -> list[str]:
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", text)]
    paragraphs = [part for part in paragraphs if part]
    if not paragraphs and text.strip():
        paragraphs = [re.sub(r"\s+", " ", text).strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 <= target_chars:
            current = f"{current}\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph
            while len(current) > target_chars * 2:
                chunks.append(current[:target_chars])
                current = current[target_chars:]
    if current:
        chunks.append(current)
    return chunks


def embed(text: str) -> list[float]:
    counts: Counter[int] = Counter()
    for token in re.findall(r"[\w-]{2,}", normalize(text)):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        counts[int.from_bytes(digest, "big") % EMBEDDING_DIMENSIONS] += 1
    vector = [float(counts[index]) for index in range(EMBEDDING_DIMENSIONS)]
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def dumps_embedding(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))
