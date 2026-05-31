import sys
import os
import time

# Add core to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))

from remembr_memory import ReMEmbRMemory

def run_remembr_test():
    db_path = "/tmp/test_omnia_remembr.json"
    
    # Ensure clean start
    if os.path.exists(db_path):
        os.remove(db_path)
        
    print(f"Initializing ReMEmbRMemory at {db_path}...")
    mem_db = ReMEmbRMemory(db_path=db_path)
    
    # Add some mock memories
    memories_to_add = [
        {
            "caption": "A blue car is parked near the loading dock in the warehouse.",
            "detections": ["blue car"],
            "telemetry": {"latitude": 37.7749, "longitude": -122.4194, "altitude": 2.5, "bearing": 90.0},
            "local_xy": {"x": 5.0, "y": -5.0}
        },
        {
            "caption": "A red toolbox is lying on the concrete floor next to some metal shelves.",
            "detections": ["red toolbox"],
            "telemetry": {"latitude": 37.7750, "longitude": -122.4193, "altitude": 2.4, "bearing": 45.0},
            "local_xy": {"x": 10.0, "y": 8.0}
        },
        {
            "caption": "An injured casualty is lying flat on a safety vest on the ground.",
            "detections": ["person", "safety vest"],
            "telemetry": {"latitude": 37.7748, "longitude": -122.4195, "altitude": 1.5, "bearing": 180.0},
            "local_xy": {"x": -2.0, "y": -3.0}
        }
    ]
    
    print("\nAdding mock visual memories to database:")
    for m in memories_to_add:
        mem_id = mem_db.add_memory(
            caption=m["caption"],
            detections=m["detections"],
            gps=m["telemetry"],
            local_xy=(m["local_xy"]["x"], m["local_xy"]["y"]),
            altitude=m["telemetry"]["altitude"],
            bearing=m["telemetry"]["bearing"],
            drone_id="drone_alpha"
        )
        print(f" - Stored memory {mem_id}: '{m['caption'][:40]}...' at XY=({m['local_xy']['x']}, {m['local_xy']['y']})")
        # Sleep briefly to ensure distinct timestamps
        time.sleep(0.1)
        
    # Get summary
    summary = mem_db.get_memory_summary()
    print(f"\nDatabase Summary: {summary}")
    assert summary["total_memories"] == 3
    assert "blue car" in summary["unique_detections"]
    assert "red toolbox" in summary["unique_detections"]
    assert "person" in summary["unique_detections"]
    
    # 1. Semantic Text Queries
    print("\nTesting Semantic Query 1: 'where is the tool box?'")
    results = mem_db.query_by_text("where is the tool box?", top_k=2)
    for idx, (res, score) in enumerate(results):
        print(f" Match {idx+1}: score={score:.4f} | xy=({res['local_xy']['x']}, {res['local_xy']['y']}) | caption='{res['caption']}'")
    assert "toolbox" in results[0][0]["caption"].lower()
    
    print("\nTesting Semantic Query 2: 'injured person lying down'")
    results = mem_db.query_by_text("injured person lying down", top_k=2)
    for idx, (res, score) in enumerate(results):
        print(f" Match {idx+1}: score={score:.4f} | xy=({res['local_xy']['x']}, {res['local_xy']['y']}) | caption='{res['caption']}'")
    assert "casualty" in results[0][0]["caption"].lower() or "person" in results[0][0]["caption"].lower()
    
    # 2. Spatial Query
    print("\nTesting Spatial Proximity Query around coordinates X=4.0, Y=-4.0:")
    spatial_results = mem_db.query_by_location(4.0, -4.0, radius=3.0)
    for res, dist in spatial_results:
        print(f" Found within 3.0m: distance={dist:.2f}m | caption='{res['caption']}'")
    assert len(spatial_results) == 1
    assert "blue car" in spatial_results[0][0]["caption"]
    
    # 3. Detection-based Queries
    print("\nTesting Detection Query for class: 'safety vest'")
    detection_results = mem_db.query_by_detection("safety vest")
    for res in detection_results:
        print(f" Found vest memory: caption='{res['caption']}'")
    assert len(detection_results) == 1
    
    print("\nAll ReMEmbRMemory unit tests PASSED successfully!")
    
    # Clean up
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    run_remembr_test()
