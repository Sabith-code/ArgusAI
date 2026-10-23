import logging
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model_instance: Optional[SentenceTransformer] = None

def get_embedding_model() -> SentenceTransformer:
    """Singleton loader for BAAI/bge-small-en-v1.5 on CPU."""
    global _model_instance
    if _model_instance is None:
        logger.info(f"Loading embedding model '{MODEL_NAME}' on CPU...")
        _model_instance = SentenceTransformer(MODEL_NAME, device="cpu")
        logger.info(f"Embedding model '{MODEL_NAME}' loaded successfully.")
    return _model_instance

def chunk_text(text: str, chunk_words: int = 400) -> List[str]:
    """Split text into non-overlapping chunks of ~400 words."""
    words = text.strip().split()
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), chunk_words):
        chunk_str = " ".join(words[i:i + chunk_words])
        if chunk_str.strip():
            chunks.append(chunk_str)
    return chunks

def generate_mention_embedding(item: dict) -> List[float]:
    """
    Generate a single 384-dimensional L2-normalized embedding for a mention
    using the approved Dual-Head Pooling Strategy D:
    
    V_head = L2Normalize(Embed("Title: " + title + "\nSnippet: " + snippet))
    V_body = L2Normalize(Mean(V_chunk_i)) across 400-word body chunks
    V_final = L2Normalize(0.5 * V_head + 0.5 * V_body)
    """
    model = get_embedding_model()
    
    title = (item.get("title") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    text = (item.get("text") or "").strip()
    scope = item.get("classification_scope", "")
    
    header_str = f"Title: {title}\nSnippet: {snippet}".strip()
    
    # Fallback or empty text records
    if scope == "snippet_fallback" or not text:
        vec = model.encode(header_str, normalize_embeddings=True)
        return vec.astype(float).tolist()
    
    # Full-text records: Dual-head pooling
    v_head = model.encode(header_str, normalize_embeddings=True)
    
    chunks = chunk_text(text, chunk_words=400)
    if not chunks:
        return v_head.astype(float).tolist()
    
    # Encode all body chunks
    chunk_vecs = model.encode(chunks, normalize_embeddings=True)
    v_body_raw = np.mean(chunk_vecs, axis=0)
    body_norm = np.linalg.norm(v_body_raw)
    v_body = v_body_raw / body_norm if body_norm > 0 else v_head
    
    # Dual-head 50/50 weighted combination & final L2 normalization
    v_comb_raw = 0.5 * v_head + 0.5 * v_body
    comb_norm = np.linalg.norm(v_comb_raw)
    v_final = v_comb_raw / comb_norm if comb_norm > 0 else v_head
    
    return v_final.astype(float).tolist()
