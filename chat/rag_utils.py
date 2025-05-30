import os
import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer

# ------- Configuration -------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_FILE = "faiss_index.bin"
META_FILE = "faiss_meta.npy"
EMBED_DIM = 384  # For MiniLM-L6-v2

# ------- Globals -------
embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
faiss_index = None
faiss_meta = []

# ------- FAISS Helpers -------
def save_faiss_index(index_file=INDEX_FILE, meta_file=META_FILE):
    global faiss_index, faiss_meta
    if faiss_index is not None:
        faiss.write_index(faiss_index, index_file)
        np.save(meta_file, np.array(faiss_meta, dtype=object))
        print(f"[DEBUG] FAISS index and metadata saved ({index_file}, {meta_file})")

def load_faiss_index(index_file=INDEX_FILE, meta_file=META_FILE):
    global faiss_index, faiss_meta
    if os.path.exists(index_file) and os.path.exists(meta_file):
        faiss_index = faiss.read_index(index_file)
        faiss_meta = np.load(meta_file, allow_pickle=True).tolist()
        print(f"[DEBUG] FAISS index and metadata loaded ({index_file}, {meta_file})")
    else:
        print("[DEBUG] FAISS index/meta files not found. Please ingest first.")

# ------- Embedding -------
def embed_texts(texts):
    return embedder.encode(texts, show_progress_bar=True)

# ------- Ingestion -------
def ingest_excel(file_path, incident_type):
    """
    Reads an Excel file and adds each row as a vector into the FAISS index.
    Each entry is [description, metadata_dict].
    """
    global faiss_index, faiss_meta
    print(f"Ingesting {file_path} for incident type: {incident_type}")
    df = pd.read_excel(file_path)
    # You might need to adjust these columns as per your data
    desc_col = "Description" if "Description" in df.columns else df.columns[0]
    meta_cols = [col for col in df.columns if col != desc_col]

    descs = df[desc_col].astype(str).tolist()
    embeddings = embed_texts(descs)

    # Build metadata dicts
    metas = []
    for i, row in df.iterrows():
        meta = {col: str(row[col]) for col in meta_cols}
        meta['incident_type'] = incident_type
        meta['description'] = str(row[desc_col])  # Ensure description field exists!
        metas.append(meta)


    # Initialize index if needed
    if faiss_index is None:
        faiss_index = faiss.IndexFlatL2(EMBED_DIM)
        faiss_meta = []
    # Add to index
    faiss_index.add(np.array(embeddings, dtype=np.float32))
    faiss_meta.extend(metas)
    print(f"[DEBUG] Ingested {len(descs)} records from {file_path}.")

# ------- Query -------
def search_similar_incidents(query, top_k=5):
    """
    Returns the top_k most similar incidents to the query.
    """
    global faiss_index, faiss_meta
    if faiss_index is None or faiss_index.ntotal == 0:
        print("[DEBUG] FAISS index is empty. Did you ingest or load?")
        return []
    q_vec = embed_texts([query])
    D, I = faiss_index.search(np.array(q_vec, dtype=np.float32), top_k)
    results = []
    for idx in I[0]:
        if idx < len(faiss_meta):
            results.append(faiss_meta[idx])
    return results

# Example usage pattern:
# Only needed ONCE:
#   ingest_excel("myfile.xlsx", "Personal Injuries")
#   save_faiss_index()
#
# For all future use (and in your app):
#   load_faiss_index()
#   search_similar_incidents("Burn injury in furnace area")

