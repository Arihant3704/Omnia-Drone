import json
import time

def prepare_state():
    # 1. Dashboard State
    state_data = {
        "telemetry": {
            "latitude": 47.397742,
            "longitude": 8.545594,
            "altitude": 2.2,
            "bearing": 90.0
        },
        "mission_mode": "COURIER",
        "mission_phase": "Scanning Target Area in Q1",
        "payload_status": "READY",
        "alert_message": "None",
        "action": "HOVER",
        "action_data": {"x": 5.2, "y": 4.8},
        "detections": ["person", "hardhat"],
        "scene_description": "An injured worker wearing a yellow hardhat is lying flat on the warehouse floor near concrete pillars.",
        "thinking": "{\n  \"thought\": \"I have scanned Quadrant 1 and detected a casualty matching the search profile (person + hardhat). Registering location X=5.2, Y=4.8 in long-horizon ReMEmbR memory database and initiating hover stabilization.\",\n  \"action\": \"HOVER\",\n  \"parameters\": {\"duration\": 10}\n}",
        "history": [
            {"latitude": 47.397742, "longitude": 8.545594},
            {"latitude": 47.397745, "longitude": 8.545598},
            {"latitude": 47.397750, "longitude": 8.545605}
        ],
        "memories": {
            "active_drones": {
                "drone_1": {
                    "latitude": 47.397742,
                    "longitude": 8.545594,
                    "status": "COURIER",
                    "phase": "Scanning Q1",
                    "trajectory": [
                        {"latitude": 47.397742, "longitude": 8.545594},
                        {"latitude": 47.397745, "longitude": 8.545598},
                        {"latitude": 47.397750, "longitude": 8.545605}
                    ]
                },
                "drone_2": {
                    "latitude": 47.397830,
                    "longitude": 8.545480,
                    "status": "SAR_RESCUE",
                    "phase": "Inspecting barrel in NW Q2",
                    "trajectory": [
                        {"latitude": 47.397820, "longitude": 8.545470},
                        {"latitude": 47.397830, "longitude": 8.545480}
                    ]
                }
            },
            "saved_facts": [
                "Quadrant 4 contains the white hospital drop zone.",
                "Quadrant 3 is flooded and has simulated blue water plane.",
                "SOP: Drone must not fly higher than 3.0m within industrial zones."
            ],
            "lessons_learned": [
                {
                    "timestamp": "2026-05-31T22:10:00.000000",
                    "drone_id": "drone_1",
                    "action": "hover",
                    "outcome": "Collision avoidance triggers immediately when obstacles are closer than 1.5m."
                },
                {
                    "timestamp": "2026-05-31T22:05:00.000000",
                    "drone_id": "drone_1",
                    "action": "rtl",
                    "outcome": "Low battery warnings should trigger immediate RTL (Return to Launch)."
                }
            ],
            "quadrants": {
                "Quadrant 1": "Casualty warehouse floor bay",
                "Quadrant 2": "Industrial shelves with toolboxes",
                "Quadrant 3": "Flooded zone",
                "Quadrant 4": "Hospital drop zone"
            },
            "waypoints": {
                "Home": {"x": 4.0, "y": -4.0},
                "Hospital": {"x": 6.0, "y": -6.0}
            }
        }
    }
    
    # 2. Map State
    map_data = {
        "obstacles": [
            [0.0, 2.0], [0.0, -2.0], [4.0, 0.0], [-4.0, 0.0],
            [1.0, 2.0], [2.0, 2.0], [-2.0, -2.0], [-1.0, -2.0]
        ],
        "drones": {
            "drone_1": {
                "x": 5.2,
                "y": 4.8,
                "z": 2.2,
                "bearing": 90.0,
                "trajectory": [
                    [0.0, 0.0], [2.0, 2.0], [5.2, 4.8]
                ]
            },
            "drone_2": {
                "x": -8.0,
                "y": 9.0,
                "z": 2.6,
                "bearing": 315.0,
                "trajectory": [
                    [0.0, 0.0], [-4.0, 4.0], [-8.0, 9.0]
                ]
            }
        }
    }
    
    with open("/tmp/omnia_dashboard_state.json", "w") as f:
        json.dump(state_data, f)
        
    with open("/tmp/omnia_map.json", "w") as f:
        json.dump(map_data, f)
        
    print("Dashboard and SLAM map mock states prepared in /tmp!")

if __name__ == "__main__":
    prepare_state()
