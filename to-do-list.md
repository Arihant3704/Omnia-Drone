# Omnia Project To-Do List

This document tracks completed tasks and remaining items for the local Agentic Drone search-and-rescue simulation project.

---

## ✅ Completed Tasks

- **Local Vision-Language Model (VLM) Integration**:
  - Integrated local **Moondream VLM** via Ollama to describe simulation frames (eliminating dependency on Gemini/cloud vision APIs).
  - Designed a 2-step local pipeline: Moondream processes visual frames -> Qwen2.5 processes scene descriptions + telemetry to output movement decisions.
  - Successfully pulled `moondream` (1.7 GB) and `qwen2.5:0.5b` (397 MB) into the local Ollama registry.

- **4-Quadrant High-Realism Partition Environment**:
  - Structured the Gazebo simulation world (`sar_demo.world`) into 4 quadrants separated by `grey_wall` partitions.
  - Created scenario-specific assets:
    - **Q1**: Fallen casualty warehouse floor bay.
    - **Q2**: Industrial shelves and red search toolbox.
    - **Q3**: Flooded blue water plane with a drowning casualty.
    - **Q4**: Home (green) and Hospital (white) building zones.

- **Persistent JSON Memory & Agent Context Injection**:
  - Implemented local persistent storage at `/tmp/omnia_memory.json` tracking waypoints, quadrant layout descriptions, and operator-injected facts.
  - Added operator facts ingestion (`remember that ...`) storing records dynamically to memory.
  - Structured the system prompt to inject active persistent memories, giving the VLM continuous context of the environment scenery.

- **Cartesian Coordinate Navigation Overrides**:
  - Coded mathematical conversion translating raw Latitude/Longitude coordinates into local Cartesian meter offsets ($X$, $Y$) relative to launch origin.
  - Enabled direct navigation to mapped targets: `Home` ($X=4.0, Y=-4.0$), `Hospital` ($X=6.0, Y=-6.0$), and `Origin` ($0.0, 0.0$).
  - Added support for operator coordinate override commands (e.g. "fly to hospital") that interrupt mission routines and steer the drone directly.

- **MAVLink Controller & Failsafes**:
  - Resolved `OFFBOARD` transition timeouts by streaming setpoints at 10Hz.
  - Temporarily disabled offboard setpoints during mode changes (to `LAND` or `RTL`) to prevent PX4 from rejecting mode switches.
  - Fixed a blocking bug in the controller's telemetry status loop by using non-blocking file descriptors (`os.O_NONBLOCK`) for the IPC FIFO pipes.
  - Set the auto-takeoff altitude threshold to `1.0m` to prevent redundant takeoff actions when the drone is already airborne.

- **Streamlit Control Dashboard Upgrade**:
  - Redesigned Streamlit control panel (`dashboard.py`) with a dedicated **Pilot Persistent Memory Base** card showing saved facts, quadrant data, and waypoint coords.
  - Added **Quick Navigation Overrides** control buttons (`Fly to Home`, `Fly to Hospital`, `Return to Base`) for instant trajectory commands.

---

- [x] **Knowledge Retrieval (RAG)**:
  - Create a local Standard Operating Procedure (SOP) manual for SAR drone missions.
  - Implement a retrieval mechanism (semantic or keyword) to inject relevant Top-K context into the LLM system prompt.
- [x] **Reflection & Learning Loop**:
  - Implement a post-action evaluation step that checks the execution results against expected outcomes.
  - Dynamically write "Lessons Learned" and outcome insights into `/tmp/omnia_memory.json`.
- [x] **Dynamic Obstacle Avoidance**:
  - Integrate distance sensor data (PX4 lidar or sonar rangefinders) to avoid colliding with `grey_wall` dividers when traversing quadrants.
- [x] **Multi-drone Cooperative Missions**:
  - Expand the telemetry and JSON memory format to support cooperative multi-agent setups where multiple drones update and sync a shared memory map.
- [x] **NVIDIA ReMEmbR Spatio-Temporal Memory**:
  - Created `remembr_memory.py` vector database module using SentenceTransformers (`all-MiniLM-L6-v2`) and NumPy-based cosine similarity.
  - Implemented continuous VLM captioning and deduplication on the agent pilot control loop, storing memories with visual descriptions, YOLO detections, and 3D coordinate metadata.
  - Added semantic query tools to the LLM pilot loop, enabling natural language command navigation overrides.
  - Developed the "🧠 NVIDIA ReMEmbR Vector DB" dashboard interface in Streamlit, supporting live semantic searches, database metrics, and a chronological visual memory timeline.

