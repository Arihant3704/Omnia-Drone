import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))

from remembr_memory import ReMEmbRMemory

def prepare():
    db_path = "/tmp/omnia_remembr.json"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    print("Initializing mock memories for ReMEmbR dashboard demonstration...")
    mem_db = ReMEmbRMemory(db_path=db_path)
    
    memories = [
        {
            "caption": "An injured worker wearing a yellow hardhat is lying flat on the warehouse floor near concrete pillars.",
            "detections": ["person", "hardhat"],
            "gps": {"latitude": 47.397742, "longitude": 8.545594},
            "local_xy": (5.2, 4.8),
            "altitude": 2.2,
            "bearing": 90.0,
            "drone_id": "drone_1"
        },
        {
            "caption": "A bright red steel toolbox is visible on the lower shelf of the industrial storage rack.",
            "detections": ["red toolbox"],
            "gps": {"latitude": 47.397800, "longitude": 8.545500},
            "local_xy": (-5.0, 5.0),
            "altitude": 2.5,
            "bearing": 270.0,
            "drone_id": "drone_1"
        },
        {
            "caption": "A blue cargo truck is parked in the loading dock bay at the rear entrance.",
            "detections": ["blue car"],
            "gps": {"latitude": 47.397700, "longitude": 8.545650},
            "local_xy": (5.5, -4.5),
            "altitude": 2.5,
            "bearing": 45.0,
            "drone_id": "drone_1"
        },
        {
            "caption": "A high-visibility orange safety vest is discarded on the floor near some scattered debris.",
            "detections": ["safety vest"],
            "gps": {"latitude": 47.397650, "longitude": 8.545500},
            "local_xy": (-5.0, -5.0),
            "altitude": 1.8,
            "bearing": 180.0,
            "drone_id": "drone_1"
        },
        {
            "caption": "A second casualty is spotted near the medical supplies building, appearing conscious but unable to walk.",
            "detections": ["person"],
            "gps": {"latitude": 47.397710, "longitude": 8.545550},
            "local_xy": (2.1, -1.5),
            "altitude": 2.0,
            "bearing": 120.0,
            "drone_id": "drone_2"
        },
        {
            "caption": "Scattered wood planks and concrete rubble blocking the central pathway between Quadrants 2 and 3.",
            "detections": ["debris"],
            "gps": {"latitude": 47.397750, "longitude": 8.545450},
            "local_xy": (-2.0, 0.5),
            "altitude": 2.4,
            "bearing": 0.0,
            "drone_id": "drone_1"
        },
        {
            "caption": "A metal drum barrel containing unknown chemical markings sits in the northwest corner of the facility.",
            "detections": ["barrel"],
            "gps": {"latitude": 47.397830, "longitude": 8.545480},
            "local_xy": (-8.0, 9.0),
            "altitude": 2.6,
            "bearing": 315.0,
            "drone_id": "drone_2"
        }
    ]
    
    for m in memories:
        mem_db.add_memory(
            caption=m["caption"],
            detections=m["detections"],
            local_xy=m["local_xy"],
            gps=m["gps"],
            altitude=m["altitude"],
            bearing=m["bearing"],
            drone_id=m["drone_id"]
        )
        time.sleep(0.1)
        
    mem_db.flush()
    print(f"Successfully generated {len(memories)} semantic memories in {db_path}!")

if __name__ == "__main__":
    prepare()
