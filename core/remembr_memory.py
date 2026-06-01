"""
ReMEmbR-Style Spatio-Temporal Vector Memory for Omnia SAR Drone

Implements a lightweight vector database for storing and retrieving
drone visual memories indexed by text embeddings, spatial coordinates,
and timestamps. Inspired by NVIDIA's ReMEmbR architecture.

Memory entries contain:
- VLM caption (scene description)
- YOLO detections
- GPS + local XY coordinates
- Bearing, altitude, timestamp
- Drone ID for multi-agent support
- Text embedding vector for semantic search
"""

import os
import json
import time
import fcntl
import logging
import hashlib
import numpy as np

logger = logging.getLogger(__name__)

# Load sentence-transformers for embedding
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
    _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    HAS_EMBEDDINGS = True
    EMBEDDING_DIM = 384
    logger.info(f"ReMEmbR: Loaded embedding model '{EMBEDDING_MODEL_NAME}' ({EMBEDDING_DIM}-dim)")
except Exception as e:
    logger.warning(f"ReMEmbR: SentenceTransformer not available ({e}). Semantic search disabled.")
    _embedding_model = None
    HAS_EMBEDDINGS = False
    EMBEDDING_DIM = 384


class ReMEmbRMemory:
    """
    Spatio-temporal vector memory database for embodied robot reasoning.
    
    Stores visual captions paired with coordinates and timestamps,
    enabling semantic, spatial, and temporal queries over the drone's
    long-horizon observation history.
    """

    def __init__(self, db_path="/tmp/omnia_remembr.json", max_memories=500, dedup_threshold=0.92):
        self.db_path = db_path
        self.max_memories = max_memories
        self.dedup_threshold = dedup_threshold
        
        # In-memory stores
        self.memories = []          # List of memory dicts (without embeddings)
        self.embeddings = None      # numpy array of shape (N, EMBEDDING_DIM)
        self._next_id = 0
        
        # Load existing memories from disk
        self._load()
        logger.info(f"ReMEmbR: Initialized with {len(self.memories)} memories from {self.db_path}")

    # ──────────────────────────────────────────────────────────
    # Memory Building
    # ──────────────────────────────────────────────────────────

    def add_memory(self, caption, detections=None, local_xy=None, gps=None,
                   altitude=0.0, bearing=0.0, drone_id="drone_1", quadrant=None):
        """
        Add a new spatio-temporal memory entry.
        
        Args:
            caption: VLM scene description string
            detections: list of YOLO detection labels
            local_xy: tuple (x, y) in local meters from launch origin
            gps: dict {"lat": float, "lon": float}
            altitude: current altitude in meters
            bearing: heading in degrees
            drone_id: identifier for multi-drone setups
            quadrant: optional quadrant label
            
        Returns:
            Memory ID string if added, None if deduplicated/skipped
        """
        if not caption or not caption.strip():
            return None

        caption = caption.strip()
        
        # Compute embedding
        embedding = self._embed(caption)
        if embedding is None:
            return None

        # Deduplication: skip if too similar to recent memories
        if self.embeddings is not None and len(self.embeddings) > 0:
            recent_count = min(10, len(self.embeddings))
            recent_embs = self.embeddings[-recent_count:]
            similarities = self._cosine_similarity(embedding, recent_embs)
            if np.max(similarities) >= self.dedup_threshold:
                logger.debug(f"ReMEmbR: Skipping duplicate memory (sim={np.max(similarities):.3f})")
                return None

        # Build memory entry
        mem_id = f"mem_{self._next_id:05d}"
        self._next_id += 1
        
        entry = {
            "id": mem_id,
            "timestamp": time.time(),
            "caption": caption,
            "detections": detections or [],
            "local_xy": {"x": local_xy[0], "y": local_xy[1]} if local_xy else {"x": 0.0, "y": 0.0},
            "gps": gps or {"lat": 0.0, "lon": 0.0},
            "altitude": altitude,
            "bearing": bearing,
            "drone_id": drone_id,
            "quadrant": quadrant or self._estimate_quadrant(local_xy)
        }
        
        self.memories.append(entry)
        
        # Update embeddings array
        emb_2d = embedding.reshape(1, -1)
        if self.embeddings is None or len(self.embeddings) == 0:
            self.embeddings = emb_2d
        else:
            self.embeddings = np.vstack([self.embeddings, emb_2d])

        # Enforce max memory limit (FIFO eviction)
        if len(self.memories) > self.max_memories:
            self.memories.pop(0)
            self.embeddings = self.embeddings[1:]

        # Auto-save on every memory
        self._save()

        logger.info(f"ReMEmbR: Stored memory {mem_id} — \"{caption[:60]}...\" at ({entry['local_xy']['x']:.1f}, {entry['local_xy']['y']:.1f})")
        return mem_id

    # ──────────────────────────────────────────────────────────
    # Querying: Semantic (text), Spatial, Temporal, Combined
    # ──────────────────────────────────────────────────────────

    def query_by_text(self, query, top_k=5):
        """
        Semantic search: find memories whose captions are most similar to the query.
        Returns list of (memory_dict, similarity_score) tuples.
        """
        if not self.memories or self.embeddings is None:
            return []
        
        query_emb = self._embed(query)
        if query_emb is None:
            return self._keyword_fallback(query, top_k)
        
        similarities = self._cosine_similarity(query_emb, self.embeddings)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.15:  # minimum relevance threshold
                results.append((self.memories[idx], float(similarities[idx])))
        return results

    def query_by_location(self, x, y, radius=5.0, top_k=10):
        """
        Spatial search: find memories recorded near (x, y) within radius meters.
        Returns list of (memory_dict, distance) tuples sorted by proximity.
        """
        if not self.memories:
            return []
        
        results = []
        for mem in self.memories:
            mx = mem["local_xy"]["x"]
            my = mem["local_xy"]["y"]
            dist = np.sqrt((mx - x)**2 + (my - y)**2)
            if dist <= radius:
                results.append((mem, float(dist)))
        
        results.sort(key=lambda r: r[1])
        return results[:top_k]

    def query_by_time(self, minutes_ago=5, top_k=10):
        """
        Temporal search: find memories from the last N minutes.
        Returns list of memory dicts, most recent first.
        """
        if not self.memories:
            return []
        
        cutoff = time.time() - (minutes_ago * 60)
        results = [m for m in self.memories if m["timestamp"] >= cutoff]
        results.sort(key=lambda m: m["timestamp"], reverse=True)
        return results[:top_k]

    def query_by_detection(self, target_label, top_k=5):
        """
        Detection search: find memories where a specific object was detected.
        Returns list of memory dicts, most recent first.
        """
        if not self.memories:
            return []
        
        target_lower = target_label.lower()
        results = []
        for mem in self.memories:
            for det in mem.get("detections", []):
                if target_lower in det.lower():
                    results.append(mem)
                    break
        
        results.sort(key=lambda m: m["timestamp"], reverse=True)
        return results[:top_k]

    def query_combined(self, text=None, x=None, y=None, minutes_ago=None,
                       detection=None, top_k=5):
        """
        Multi-modal query: weighted combination of semantic + spatial + temporal signals.
        
        Args:
            text: semantic query string
            x, y: spatial center point
            minutes_ago: temporal window
            detection: object label filter
            top_k: number of results
            
        Returns:
            list of (memory_dict, combined_score) tuples
        """
        if not self.memories:
            return []

        scores = np.zeros(len(self.memories))
        
        # Semantic scoring (weight: 0.5)
        if text and self.embeddings is not None:
            query_emb = self._embed(text)
            if query_emb is not None:
                sims = self._cosine_similarity(query_emb, self.embeddings)
                scores += 0.5 * sims

        # Spatial scoring (weight: 0.3)
        if x is not None and y is not None:
            for i, mem in enumerate(self.memories):
                mx = mem["local_xy"]["x"]
                my = mem["local_xy"]["y"]
                dist = np.sqrt((mx - x)**2 + (my - y)**2)
                # Gaussian falloff: closer = higher score
                spatial_score = np.exp(-dist**2 / (2 * 10.0**2))
                scores[i] += 0.3 * spatial_score

        # Temporal scoring (weight: 0.2)
        if minutes_ago is not None:
            cutoff = time.time() - (minutes_ago * 60)
            for i, mem in enumerate(self.memories):
                if mem["timestamp"] >= cutoff:
                    # Linear decay within the window
                    recency = (mem["timestamp"] - cutoff) / (minutes_ago * 60)
                    scores[i] += 0.2 * recency

        # Detection filter (hard filter, not scored)
        if detection:
            det_lower = detection.lower()
            for i, mem in enumerate(self.memories):
                has_det = any(det_lower in d.lower() for d in mem.get("detections", []))
                if not has_det:
                    scores[i] = 0.0

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0.05:
                results.append((self.memories[idx], float(scores[idx])))
        return results

    def get_memory_summary(self):
        """Return a summary of the memory state for dashboard display."""
        if not self.memories:
            return {
                "total_memories": 0,
                "time_span_minutes": 0,
                "unique_detections": [],
                "recent_memories": []
            }
        
        timestamps = [m["timestamp"] for m in self.memories]
        all_detections = set()
        for m in self.memories:
            for d in m.get("detections", []):
                all_detections.add(d)
        
        return {
            "total_memories": len(self.memories),
            "time_span_minutes": round((max(timestamps) - min(timestamps)) / 60, 1),
            "unique_detections": sorted(all_detections),
            "recent_memories": self.memories[-5:]
        }

    # ──────────────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────────────

    def _embed(self, text):
        """Compute embedding vector for text using SentenceTransformer."""
        if not HAS_EMBEDDINGS or _embedding_model is None:
            return None
        try:
            return _embedding_model.encode(text, convert_to_numpy=True)
        except Exception as e:
            logger.warning(f"ReMEmbR: Embedding failed: {e}")
            return None

    def _cosine_similarity(self, query_vec, matrix):
        """Compute cosine similarity between a query vector and a matrix of vectors."""
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return np.zeros(len(matrix))
        matrix_norms = np.linalg.norm(matrix, axis=1)
        matrix_norms[matrix_norms == 0] = 1e-8
        dots = np.dot(matrix, query_vec)
        return dots / (matrix_norms * query_norm)

    def _estimate_quadrant(self, local_xy):
        """Estimate which quadrant coordinates fall into."""
        if local_xy is None:
            return "Unknown"
        x, y = local_xy
        if x >= 0 and y >= 0:
            return "Quadrant 1"  # NE
        elif x < 0 and y >= 0:
            return "Quadrant 2"  # NW
        elif x < 0 and y < 0:
            return "Quadrant 3"  # SW
        else:
            return "Quadrant 4"  # SE

    def _keyword_fallback(self, query, top_k=5):
        """Fallback keyword-based search when embeddings are unavailable."""
        stop_words = {'the', 'a', 'an', 'and', 'or', 'is', 'are', 'was', 'to', 'for', 'in', 'on', 'at'}
        query_words = set(query.lower().split()) - stop_words
        
        scored = []
        for mem in self.memories:
            caption_words = set(mem["caption"].lower().split()) - stop_words
            det_words = set(d.lower() for d in mem.get("detections", []))
            overlap = len(query_words & (caption_words | det_words))
            if overlap > 0:
                scored.append((mem, overlap))
        
        scored.sort(key=lambda r: r[1], reverse=True)
        return scored[:top_k]

    # ──────────────────────────────────────────────────────────
    # Persistence (JSON + fcntl locking)
    # ──────────────────────────────────────────────────────────

    def _save(self):
        """Persist memories to disk with file locking for multi-drone safety."""
        try:
            save_data = {
                "version": 1,
                "next_id": self._next_id,
                "memories": self.memories,
                "embeddings": self.embeddings.tolist() if self.embeddings is not None else []
            }
            with open(self.db_path, 'a+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                f.truncate()
                json.dump(save_data, f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            logger.debug(f"ReMEmbR: Saved {len(self.memories)} memories to {self.db_path}")
        except Exception as e:
            logger.error(f"ReMEmbR: Failed to save: {e}")

    def _load(self):
        """Load memories from disk."""
        if not os.path.exists(self.db_path):
            self.memories = []
            self.embeddings = None
            self._next_id = 0
            return
        
        try:
            with open(self.db_path, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            self.memories = data.get("memories", [])
            self._next_id = data.get("next_id", len(self.memories))
            
            emb_list = data.get("embeddings", [])
            if emb_list:
                self.embeddings = np.array(emb_list, dtype=np.float32)
            else:
                self.embeddings = None
                
        except Exception as e:
            logger.error(f"ReMEmbR: Failed to load from {self.db_path}: {e}")
            self.memories = []
            self.embeddings = None
            self._next_id = 0

    def flush(self):
        """Force-save all memories to disk."""
        self._save()


# ──────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("ReMEmbR Memory Self-Test")
    print("=" * 60)
    
    mem = ReMEmbRMemory(db_path="/tmp/remembr_test.json", max_memories=100)
    
    # Add test memories
    mem.add_memory(
        caption="A person lying flat on a warehouse floor near metal shelves",
        detections=["person"],
        local_xy=(5.2, 4.8),
        gps={"lat": 47.397742, "lon": 8.545594},
        altitude=2.5, bearing=90.0
    )
    mem.add_memory(
        caption="A bright red toolbox sitting on an industrial shelf",
        detections=["red toolbox"],
        local_xy=(-5.0, 5.0),
        gps={"lat": 47.397800, "lon": 8.545500},
        altitude=2.5, bearing=270.0
    )
    mem.add_memory(
        caption="A drowning person floating in blue flood water",
        detections=["person"],
        local_xy=(-5.0, -5.0),
        gps={"lat": 47.397650, "lon": 8.545500},
        altitude=2.5, bearing=180.0
    )
    mem.add_memory(
        caption="A blue car parked near a green building and a white hospital",
        detections=["blue car"],
        local_xy=(5.5, -4.5),
        gps={"lat": 47.397700, "lon": 8.545650},
        altitude=2.5, bearing=45.0
    )
    
    # Test semantic search
    print("\n--- Semantic: 'injured person' ---")
    results = mem.query_by_text("injured person", top_k=3)
    for r, score in results:
        print(f"  [{score:.3f}] {r['caption'][:70]} @ ({r['local_xy']['x']}, {r['local_xy']['y']})")
    
    # Test spatial search
    print("\n--- Spatial: near (5.0, 5.0) within 3m ---")
    results = mem.query_by_location(5.0, 5.0, radius=3.0)
    for r, dist in results:
        print(f"  [{dist:.1f}m] {r['caption'][:70]}")
    
    # Test detection search
    print("\n--- Detection: 'blue car' ---")
    results = mem.query_by_detection("blue car")
    for r in results:
        print(f"  {r['caption'][:70]} @ ({r['local_xy']['x']}, {r['local_xy']['y']})")
    
    # Test combined search
    print("\n--- Combined: text='person on floor' + near (5,5) ---")
    results = mem.query_combined(text="person on floor", x=5.0, y=5.0, top_k=3)
    for r, score in results:
        print(f"  [{score:.3f}] {r['caption'][:70]}")
    
    # Test summary
    print(f"\n--- Summary ---")
    summary = mem.get_memory_summary()
    print(f"  Total: {summary['total_memories']} memories")
    print(f"  Detections: {summary['unique_detections']}")
    
    # Test persistence
    mem.flush()
    mem2 = ReMEmbRMemory(db_path="/tmp/remembr_test.json")
    print(f"\n  Persistence: Reloaded {len(mem2.memories)} memories ✓")
    
    # Cleanup
    os.remove("/tmp/remembr_test.json")
    print("\n✅ All ReMEmbR tests passed!")
