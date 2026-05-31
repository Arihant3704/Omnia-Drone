import os
import re
import numpy as np

# Try to load SentenceTransformer for local embedding retrieval
try:
    from sentence_transformers import SentenceTransformer
    # Using a standard lightweight embedding model
    EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    HAS_EMBEDDINGS = True
except Exception as e:
    print(f"RAG WARNING: SentenceTransformer not initialized ({e}). Falling back to Keyword search.")
    HAS_EMBEDDINGS = False

class RAGRetriever:
    def __init__(self, filepath=None):
        if filepath is None:
            # Resolve absolute path relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.filepath = os.path.join(base_dir, "sar_sop_manual.md")
        else:
            self.filepath = filepath
        
        self.chunks = []
        self.chunk_embeddings = None
        self.load_and_chunk_manual()
        self.compute_embeddings()

    def load_and_chunk_manual(self):
        """Parse the markdown SOP manual into distinct sections/chunks."""
        if not os.path.exists(self.filepath):
            # Fallback default rules if file is missing
            self.chunks = [
                "FLIGHT SAFETY: Cruise altitude is 2.5 meters. Visual sweep altitude is 1.0 meters.",
                "QUADRANT 1: NE area floor casualty must be logged as FALLEN.",
                "QUADRANT 2: Search for red toolbox on shelves and drop life jacket.",
                "QUADRANT 3: SW flooded area drowning casualty must be logged as DROWNING.",
                "WAYPOINTS: Home X=4.0 Y=-4.0, Hospital X=6.0 Y=-6.0, Origin X=0.0 Y=0.0."
            ]
            return

        with open(self.filepath, 'r') as f:
            content = f.read()

        # Split content by markdown headers (## SECTION ...)
        raw_sections = re.split(r'(?=## SECTION)', content)
        
        for section in raw_sections:
            section = section.strip()
            if not section:
                continue
            # Keep markdown headers and text together as a logical chunk
            self.chunks.append(section)

        if not self.chunks:
            self.chunks = ["No SOP manual chunks available."]

    def compute_embeddings(self):
        """Pre-compute embeddings for all chunks if sentence-transformers is available."""
        if HAS_EMBEDDINGS:
            try:
                self.chunk_embeddings = embedding_model.encode(self.chunks, convert_to_numpy=True)
            except Exception as e:
                print(f"RAG ERROR: Failed to compute chunk embeddings: {e}")
                self.chunk_embeddings = None

    def retrieve_keyword(self, query, top_k=2):
        """Fallback keyword overlap retrieval algorithm."""
        # Simple stop words list
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'to', 'for', 'in', 'on', 'at', 'by', 'of', 'with'}
        
        query_words = set(re.findall(r'\w+', query.lower())) - stop_words
        scores = []

        for chunk in self.chunks:
            chunk_words = set(re.findall(r'\w+', chunk.lower())) - stop_words
            # Calculate word intersection size as simple score
            intersection = query_words.intersection(chunk_words)
            scores.append(len(intersection))

        # Get indices of top scores
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [self.chunks[idx] for idx in top_indices]

    def retrieve(self, query, top_k=2):
        """Retrieve the top-K relevant SOP chunks for a query."""
        if HAS_EMBEDDINGS and self.chunk_embeddings is not None:
            try:
                query_emb = embedding_model.encode([query], convert_to_numpy=True)[0]
                # Compute cosine similarity
                dot_products = np.dot(self.chunk_embeddings, query_emb)
                norms = np.linalg.norm(self.chunk_embeddings, axis=1) * np.linalg.norm(query_emb)
                similarities = dot_products / (norms + 1e-8)
                
                top_indices = np.argsort(similarities)[::-1][:top_k]
                return [self.chunks[idx] for idx in top_indices]
            except Exception as e:
                print(f"RAG Error during retrieval: {e}. Falling back to keyword search.")
                return self.retrieve_keyword(query, top_k)
        else:
            return self.retrieve_keyword(query, top_k)

if __name__ == "__main__":
    # Self-test
    retriever = RAGRetriever()
    print("--- Test retrieval for 'hospital building' ---")
    print(retriever.retrieve("hospital building", top_k=1))
    print("\n--- Test retrieval for 'altitude' ---")
    print(retriever.retrieve("cruising altitude for sweep", top_k=1))
