# Omnia Search and Rescue Agentic Pilot (PolluxPenguin)

An autonomous, agentic search-and-rescue (SAR) drone pilot system powered by local vision-language models (VLMs), real-time open-vocabulary object detection, and the PX4 Autopilot simulator in Gazebo.

---

## 🛠 System Overview

The system consists of three main components:
1. **Gazebo Simulator (PX4 SITL)**: Simulates the drone (equipped with a camera sensor) flying in a custom warehouse world populated with search targets.
2. **MAVLink Controller (`controller.py`)**: A Python-based flight controller that handles drone telemetry, failsafes, smart auto-takeoff, landing, and precise velocity-based movement commands via a non-blocking FIFO API.
3. **Agentic Pilot (`agent_pilot_pseudolive.py`)**: The reasoning core that runs a vision + reasoning loop:
   - Captures camera frames from the simulation viewport.
   - Runs open-vocabulary detection using **YOLO-World** (`yolov8s-world.pt`) for instant localized detection.
   - Utilizes **Moondream VLM** (local) to describe the scene in detail.
   - Feeds the telemetry, detections, and visual descriptions to a local LLM (**Qwen-2.5-0.5B**) to decide the drone's next movement or landing protocol.

---

## 📋 Prerequisites

- **OS**: Linux (Ubuntu 20.04 / 22.04 recommended)
- **Simulator**: PX4 Autopilot SITL & Gazebo Classic 11
- **Python**: Python 3.8+ with virtualenv support
- **Local AI Engine**: [Ollama](https://ollama.com) installed and running

---

## ⚙️ Setup Instructions

### 1. Install Dependencies
Install all python packages:
```bash
pip install -r requirements.txt
```

### 2. Set Up Local Models via Ollama
Ensure the Ollama service is running. Pull the required models:
```bash
# Pull the text reasoning LLM
ollama pull qwen2.5:0.5b

# Pull the visual description VLM
ollama pull moondream
```

### 3. Environment Configuration
Create or edit your `.env` file in the root directory:
```env
GOOGLE_API_KEY=
USE_OLLAMA=true
OLLAMA_MODEL=qwen2.5:0.5b
OLLAMA_VISION_MODEL=moondream
OLLAMA_HOST=http://localhost:11434
```

---

## 🚀 Running the Search & Rescue Demo

A unified launch script is provided to automate starting all simulator and agent processes.

1. **Make the script executable**:
   ```bash
   chmod +x scripts/run_sar_demo.sh
   ```

2. **Run the demo launcher**:
   ```bash
   ./scripts/run_sar_demo.sh
   ```
   *This will launch three gnome-terminal tabs:*
   - **Tab 1**: PX4 SITL simulator in Gazebo with the custom `sar_demo.world`.
   - **Tab 2**: The Drone Controller connecting to PX4 on port `14540`.
   - **Tab 3**: The local Omnia Agentic Pilot loop capturing the camera viewport and executing local model reasoning.

---

## 🗺 Custom Search and Rescue (SAR) Scenario

The demo initializes in a modified warehouse environment (`sar_demo.world`) with emergency debris, fallen pallets, and search targets that the drone must locate:
- **3 x SAR Persons**: Standing and collapsed human figures clothed in distinct red and blue.
- **2 x Red Toolboxes**: Placed in aisles and near walls.
- **2 x Safety Vests**: High-visibility orange/reflective vests lying flat on the floor.
- **1 x Blue Car**: Parked at the external loading dock.

---

## 🔌 API & Inter-Process Communication

Processes communicate asynchronously through non-blocking FIFOs in `/tmp`:
- `/tmp/gpt_command_fifo`: Receives movement commands from the LLM agent (e.g. `F5` for forward 5m, `LAND`, `L2` for left 2m).
- `/tmp/gpt_status_fifo`: Exposes real-time JSON drone telemetry (latitude, longitude, altitude, bearing).
- `/tmp/gpt_statusa_fifo`: Feeds JSON telemetry to the LLM agent.

To manually command the drone at any point:
```bash
# Command to fly forward 5 meters
echo "F5" > /tmp/gpt_command_fifo

# Command to land safely
echo "LAND" > /tmp/gpt_command_fifo
```
