from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
import pickle

class ContextEngine:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        # Load local embedding model
        self.encoder = SentenceTransformer(model_name)
        self.index_dir = "indexes"
        os.makedirs(self.index_dir, exist_ok=True)
        self.dim = self.encoder.get_sentence_embedding_dimension()
        
    def _get_index_path(self, session_id):
        return os.path.join(self.index_dir, f"{session_id}.index")
        
    def _get_meta_path(self, session_id):
        return os.path.join(self.index_dir, f"{session_id}_meta.pkl")

    def build_index(self, session_id: str, chunks: list):
        if not chunks:
            return
            
        texts = [f"File: {c['filepath']}\n{c['content']}" for c in chunks]
        embeddings = self.encoder.encode(texts, convert_to_numpy=True)
        
        # Create FAISS index
        index = faiss.IndexFlatL2(self.dim)
        index.add(embeddings)
        
        # Save index and metadata
        faiss.write_index(index, self._get_index_path(session_id))
        with open(self._get_meta_path(session_id), "wb") as f:
            pickle.dump(chunks, f)

    def has_index(self, session_id: str) -> bool:
        return os.path.exists(self._get_index_path(session_id)) and os.path.exists(self._get_meta_path(session_id))

    def search(self, session_id: str, query: str, top_k=5):
        if not self.has_index(session_id):
            return []
            
        index = faiss.read_index(self._get_index_path(session_id))
        with open(self._get_meta_path(session_id), "rb") as f:
            chunks = pickle.load(f)
            
        query_vector = self.encoder.encode([query], convert_to_numpy=True)
        distances, indices = index.search(query_vector, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(chunks):
                results.append(chunks[idx])
                
        return results
