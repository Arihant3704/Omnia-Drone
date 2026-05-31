import asyncio
import os
import time
import cv2
import json
import logging
import fcntl
import mss
import numpy as np
import subprocess
import re
from datetime import datetime
from PIL import Image
from google import genai
from google.genai import types
from ultralytics import YOLOWorld
from dotenv import load_dotenv
from rag_retriever import RAGRetriever
from remembr_memory import ReMEmbRMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OmniaPilot_PseudoLive")

# --- CONFIGURATION ---
MODEL_ID = "models/gemini-3.1-flash-lite-preview" 

def get_gazebo_viewport():
    default_vp = (1779, 238, 1081, 875)
    try:
        env = {"DISPLAY": ":1"}
        res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
        lines = res.stdout.splitlines()
        
        # 1. Search for Gazebo: Image View window in the entire tree
        camera_win_id = None
        camera_win_geom = None
        for line in lines:
            if '"Image View"' in line or '"Gazebo: Image View"' in line:
                m = re.search(r"(0x[0-9a-fA-F]+)", line)
                m_geom = re.search(r"(\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)", line)
                if m and m_geom:
                    win_id = m.group(1)
                    w = int(m_geom.group(0).split('x')[0].split()[-1]) # Safe parse width
                    # Let's extract values accurately
                    parts = line.split()
                    geom_str = parts[-2] if len(parts) >= 2 else ""
                    abs_str = parts[-1] if len(parts) >= 1 else ""
                    
                    match_g = re.search(r"(\d+)x(\d+)", geom_str)
                    match_a = re.search(r"([+-]\d+)([+-]\d+)", abs_str)
                    if match_g and match_a:
                        w = int(match_g.group(1))
                        h = int(match_g.group(2))
                        x = int(match_a.group(1))
                        y = int(match_a.group(2))
                        camera_win_id = win_id
                        camera_win_geom = (x, y, w, h)
                        break

        if camera_win_id:
            # Let's resize it to exactly 640x480 for consistent feed
            if camera_win_geom[2] != 640 or camera_win_geom[3] != 480:
                subprocess.run(["xdotool", "windowsize", camera_win_id, "640", "480"], env=env)
                time.sleep(0.5)
                # Re-query xwininfo to get new coordinates after resize
                res_win = subprocess.run(["xwininfo", "-id", camera_win_id], capture_output=True, text=True, env=env)
                for l in res_win.stdout.splitlines():
                    if "Absolute upper-left X:" in l:
                        x = int(l.split()[-1])
                    elif "Absolute upper-left Y:" in l:
                        y = int(l.split()[-1])
                camera_win_geom = (x, y, 640, 480)
            
            # Crop borders out: 10px padding on left/right, 42px header, 10px footer
            crop_x = camera_win_geom[0] + 10
            crop_y = camera_win_geom[1] + 42
            crop_w = camera_win_geom[2] - 20
            crop_h = camera_win_geom[3] - 52
            logger.info(f"Dynamically detected and cropped Gazebo camera viewport: ({crop_x}, {crop_y}, {crop_w}, {crop_h})")
            return (crop_x, crop_y, crop_w, crop_h)

        # 2. Fallback to search for main Gazebo window index and check child windows
        gazebo_win_id = None
        for line in lines:
            if '"Gazebo"' in line:
                m = re.search(r"(0x[0-9a-fA-F]+)", line)
                if m:
                    gazebo_win_id = m.group(1)
                    break
        if gazebo_win_id:
            gazebo_index = -1
            for idx, line in enumerate(lines):
                if gazebo_win_id in line:
                    gazebo_index = idx
                    break
            if gazebo_index != -1:
                fallback_win = None
                for line in lines[gazebo_index+1:]:
                    if '"gazebo"' in line:
                        m_geom = re.search(r"(\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)", line)
                        if m_geom:
                            w = int(m_geom.group(1))
                            h = int(m_geom.group(2))
                            x = int(m_geom.group(3))
                            y = int(m_geom.group(4))
                            if w > 600 and h > 400:
                                fallback_win = (x, y, w, h)
                if fallback_win:
                    logger.info(f"Dynamically detected Gazebo main viewport fallback: {fallback_win}")
                    return fallback_win
            
    except Exception as e:
        logger.error(f"Error dynamically detecting Gazebo viewport: {e}")
    return default_vp

def raise_gazebo():
    try:
        env = {"DISPLAY": ":1"}
        # Raise main Gazebo window
        res = subprocess.run(["xdotool", "search", "--name", "^Gazebo$"], capture_output=True, text=True, env=env)
        win_ids = res.stdout.strip().split()
        for win_id in win_ids:
            subprocess.run(["xdotool", "windowactivate", win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["xdotool", "windowraise", win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Raise camera window if it exists to keep it on top
        res_cam = subprocess.run(["xdotool", "search", "--name", "Image View"], capture_output=True, text=True, env=env)
        cam_win_ids = res_cam.stdout.strip().split()
        for cam_win_id in cam_win_ids:
            subprocess.run(["xdotool", "windowactivate", cam_win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["xdotool", "windowraise", cam_win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f"Error raising Gazebo window: {e}")

# --- FIFO PATHS ---
COMMAND_FIFO = '/tmp/gpt_command_fifo'
STATUS_FIFO = '/tmp/gpt_status_fifo'

class OmniaPilotPseudoLive:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        
        # Ollama config
        self.use_ollama = os.getenv("USE_OLLAMA", "False").lower() in ("true", "1", "yes")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")  # Text reasoning model
        self.ollama_vision_model = os.getenv("OLLAMA_VISION_MODEL", "moondream")  # Vision model
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        
        # Perception
        self.yolo = YOLOWorld('yolov8s-world.pt')
        self.yolo.set_classes(["person", "red toolbox", "safety vest", "blue car"])
        self.sct = mss.mss()
        
        # State
        self.telemetry = {"latitude": 0, "longitude": 0, "altitude": 0, "bearing": 0}
        self.origin_lat = None
        self.origin_lon = None
        self.targets = []
        self.history = []
        self.mission_mode = None
        self.mission_phase = "IDLE"
        self.payload_status = "None"
        self.alert_message = ""
        self.mission_step = 0
        
        # Tools Mapping
        self.tools = [self.move_drone, self.land_drone, self.see_and_report]

        # RAG System
        self.rag = RAGRetriever()

        # ReMEmbR Spatio-Temporal Vector Memory (NVIDIA ReMEmbR-style)
        self.remembr = ReMEmbRMemory(db_path="/tmp/omnia_remembr.json")
        self._last_remembr_caption = ""

        # Memory System
        self.drone_id = os.environ.get("DRONE_ID", "drone_1")
        self.memory_file = "/tmp/omnia_memory.json"
        self.init_memory()

    def init_memory(self):
        default_memory = {
            "active_drones": {},
            "quadrants": {
                "Quadrant 1": "Fallen casualty site. A person who collapsed and is lying flat on the warehouse floor. Location: X=5.0, Y=5.0.",
                "Quadrant 2": "Search warehouse. Contains shelves and a bright red search box/toolbox. Location: X=-5.0, Y=5.0.",
                "Quadrant 3": "Flood/Ocean area. A drowning casualty floating/lying flat in the water. Location: X=-5.0, Y=-5.0.",
                "Quadrant 4": "Base & Medical station. Contains Home building (green, X=4.0, Y=-4.0), Hospital building (white, X=6.0, Y=-6.0), and a blue car at Location: X=5.5, Y=-4.5."
            },
            "locations": {
                "home": {"x": 4.0, "y": -4.0},
                "hospital": {"x": 6.0, "y": -6.0},
                "origin": {"x": 0.0, "y": 0.0},
                "car": {"x": 5.5, "y": -4.5}
            },
            "detected_landmarks": {},
            "saved_facts": [
                "The drone central landing pad is at coordinate X=0, Y=0.",
                "Casualty in Quadrant 1 must be reported as FALLEN.",
                "Casualty in Quadrant 3 flood zone must be reported as DROWNING."
            ],
            "commands_history": []
        }
        if not os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(default_memory, f, indent=4)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                logger.error(f"Error initializing memory: {e}")
        self.load_memory()

    def load_memory(self):
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    self.memory = json.load(f)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                self.memory = {}
            if "active_drones" not in self.memory:
                self.memory["active_drones"] = {}
        except Exception as e:
            logger.error(f"Error loading memory: {e}")
            self.memory = {}

    def save_memory(self):
        try:
            with open(self.memory_file, 'a+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                f.truncate()
                json.dump(self.memory, f, indent=4)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    def add_saved_fact(self, fact: str):
        self.load_memory()
        if "saved_facts" not in self.memory:
            self.memory["saved_facts"] = []
        if fact not in self.memory["saved_facts"]:
            self.memory["saved_facts"].append(fact)
            self.save_memory()
            logger.info(f"New fact saved to memory: {fact}")

    def get_local_coordinates(self):
        if self.origin_lat is None or self.telemetry.get("latitude", 0) == 0:
            return 0.0, 0.0
        import math
        lat = self.telemetry.get("latitude")
        lon = self.telemetry.get("longitude")
        # 1 degree lat = 111319.5 meters
        dx = (lat - self.origin_lat) * 111319.5
        # 1 degree lon = 111319.5 * cos(lat) meters
        dy = (lon - self.origin_lon) * 111319.5 * math.cos(math.radians(self.origin_lat))
        return dx, dy

    async def reflect_on_step(self, action_type, action_data, pre_telemetry, pre_targets):
        """Perform post-action reflection and record the insights to memory."""
        # Wait a short duration to let state stabilize
        await asyncio.sleep(1.0)
        await self.get_telemetry()
        post_telemetry = self.telemetry
        post_targets = self.targets

        dx = post_telemetry.get("latitude", 0) - pre_telemetry.get("latitude", 0)
        dy = post_telemetry.get("longitude", 0) - pre_telemetry.get("longitude", 0)
        dh = post_telemetry.get("altitude", 0) - pre_telemetry.get("altitude", 0)

        # Base rule-based reflection text
        reflection_text = f"Executed {action_type}. Telemetry delta: dLat={dx:.6f}, dLon={dy:.6f}, dAlt={dh:.2f}m. Detections count: {len(post_targets)}."

        # Hybrid LLM-based reflection if Ollama is active
        if self.use_ollama:
            try:
                import requests
                prompt = f"""
                Analyze the execution outcome of the following drone search-and-rescue action:
                ACTION: {action_type} with parameters {action_data}
                PRE-ACTION TELEMETRY: {pre_telemetry}
                POST-ACTION TELEMETRY: {post_telemetry}
                PRE-ACTION TARGETS: {pre_targets}
                POST-ACTION TARGETS: {post_targets}

                Summarize the lesson learned from this action in one short sentence. Return ONLY the sentence.
                """
                payload = {
                    "model": self.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                }
                res = requests.post(f"{self.ollama_host}/api/chat", json=payload, timeout=10)
                if res.status_code == 200:
                    text = res.json().get('message', {}).get('content', '').strip()
                    if text:
                        reflection_text = text
            except Exception as e:
                logger.warning(f"Ollama reflection failed: {e}. Using fallback rule reflection.")

        # Write to lessons_learned in memory
        self.load_memory()
        if "lessons_learned" not in self.memory:
            self.memory["lessons_learned"] = []
        
        lesson = {
            "timestamp": datetime.now().isoformat(),
            "drone_id": self.drone_id,
            "action": action_type,
            "outcome": reflection_text
        }
        self.memory["lessons_learned"].append(lesson)
        if len(self.memory["lessons_learned"]) > 10:
            self.memory["lessons_learned"].pop(0)
        
        self.save_memory()
        logger.info(f"🧠 Reflection & Learning: {reflection_text}")

    def navigate_to_local_xy(self, target_x: float, target_y: float):
        dx, dy = self.get_local_coordinates()
        diff_x = target_x - dx
        diff_y = target_y - dy
        
        # Takeoff check
        if self.telemetry.get("altitude", 0.0) < 1.0:
            self.send_commands("T2.5")
            time.sleep(2)
            
        cmds = []
        if abs(diff_x) > 0.5:
            if diff_x > 0:
                cmds.append(f"F{round(diff_x, 2)}")
            else:
                cmds.append(f"B{round(abs(diff_x), 2)}")
        
        if abs(diff_y) > 0.5:
            if diff_y > 0:
                cmds.append(f"R{round(diff_y, 2)}")
            else:
                cmds.append(f"L{round(abs(diff_y), 2)}")
        
        if cmds:
            cmds_str = " ".join(cmds)
            logger.info(f"Coordinate navigation to X={target_x}, Y={target_y}. Current X={round(dx, 2)}, Y={round(dy, 2)}. Sending: {cmds_str}")
            self.send_commands(cmds_str)
            return f"Flying to coordinates: {cmds_str}"
        else:
            logger.info(f"Already at target X={target_x}, Y={target_y}")
            return "Already at target coordinates."

    async def get_telemetry(self):
        if not os.path.exists(STATUS_FIFO): return
        try:
            with open(STATUS_FIFO, 'r') as f:
                line = f.readline()
                if line:
                    self.telemetry = json.loads(line)
                    if self.origin_lat is None and self.telemetry.get("latitude", 0) != 0:
                        self.origin_lat = self.telemetry.get("latitude")
                        self.origin_lon = self.telemetry.get("longitude")
                        logger.info(f"Initialized Origin Coordinates: Lat={self.origin_lat}, Lon={self.origin_lon}")
        except: pass

    def update_slam_landmarks(self, detections):
        if not detections:
            return
        dx, dy = self.get_local_coordinates()
        x_rounded = round(dx, 2)
        y_rounded = round(dy, 2)
        
        self.load_memory()
        if "detected_landmarks" not in self.memory:
            self.memory["detected_landmarks"] = {}
            
        updated = False
        for item in detections:
            # Save or update the detected item location
            self.memory["detected_landmarks"][item] = {
                "x": x_rounded,
                "y": y_rounded,
                "detected_by": self.drone_id,
                "timestamp": time.time()
            }
            updated = True
            
        if updated:
            self.save_memory()
            logger.info(f"📍 SLAM Landmark Map Updated: {self.memory['detected_landmarks']}")

    # ──────────────────────────────────────────────────────────
    # ReMEmbR Memory Builder + Query Tools
    # ──────────────────────────────────────────────────────────

    def remembr_store_observation(self, scene_description, detections=None):
        """Store current observation into the ReMEmbR spatio-temporal vector memory."""
        if not scene_description or scene_description == "N/A":
            return
        dx, dy = self.get_local_coordinates()
        gps = {
            "lat": self.telemetry.get("latitude", 0),
            "lon": self.telemetry.get("longitude", 0)
        }
        self.remembr.add_memory(
            caption=scene_description,
            detections=detections or self.targets,
            local_xy=(dx, dy),
            gps=gps,
            altitude=self.telemetry.get("altitude", 0),
            bearing=self.telemetry.get("bearing", 0),
            drone_id=self.drone_id
        )

    def remembr_query_text(self, query, top_k=5):
        """Search what the drone has seen before by semantic similarity."""
        results = self.remembr.query_by_text(query, top_k=top_k)
        if not results:
            return "No matching memories found."
        lines = []
        for mem, score in results:
            t_ago = (time.time() - mem['timestamp']) / 60
            lines.append(
                f"[{score:.2f}] \"{mem['caption'][:80]}\" "
                f"at ({mem['local_xy']['x']:.1f}, {mem['local_xy']['y']:.1f}) "
                f"{t_ago:.0f}min ago"
            )
        return "\n".join(lines)

    def remembr_query_nearby(self, x=None, y=None, radius=5.0, top_k=5):
        """Find what was observed near a specific location."""
        if x is None or y is None:
            x, y = self.get_local_coordinates()
        results = self.remembr.query_by_location(x, y, radius=radius, top_k=top_k)
        if not results:
            return f"No memories found within {radius}m of ({x:.1f}, {y:.1f})."
        lines = []
        for mem, dist in results:
            lines.append(
                f"[{dist:.1f}m] \"{mem['caption'][:80]}\" "
                f"detections={mem['detections']}"
            )
        return "\n".join(lines)

    def remembr_query_recent(self, minutes_ago=5, top_k=5):
        """Retrieve what the drone saw in the last N minutes."""
        results = self.remembr.query_by_time(minutes_ago=minutes_ago, top_k=top_k)
        if not results:
            return f"No memories from the last {minutes_ago} minutes."
        lines = []
        for mem in results:
            t_ago = (time.time() - mem['timestamp']) / 60
            lines.append(
                f"[{t_ago:.0f}min ago] \"{mem['caption'][:80]}\" "
                f"at ({mem['local_xy']['x']:.1f}, {mem['local_xy']['y']:.1f})"
            )
        return "\n".join(lines)

    def remembr_navigate_to(self, query):
        """Navigate to a location the drone remembers seeing something.
        Returns action result string or None if not found."""
        results = self.remembr.query_by_text(query, top_k=1)
        if not results:
            return None
        mem, score = results[0]
        if score < 0.2:
            return None
        target_x = mem["local_xy"]["x"]
        target_y = mem["local_xy"]["y"]
        logger.info(f"🧠 ReMEmbR Navigation: Flying to remembered \"{mem['caption'][:50]}\" at ({target_x:.1f}, {target_y:.1f}) [sim={score:.2f}]")
        nav_result = self.navigate_to_local_xy(target_x, target_y)
        self.alert_message = f"ReMEmbR Nav: Flying to remembered location ({target_x:.1f}, {target_y:.1f})"
        return f"Navigating to remembered location: {mem['caption'][:60]} at ({target_x:.1f}, {target_y:.1f}). Nav result: {nav_result}"

    async def caption_frame(self, frame):
        """Generates visual caption using local Moondream VLM via Ollama or Google GenAI."""
        if self.use_ollama:
            try:
                import requests
                import base64
                _, jpg_buf = cv2.imencode('.jpg', frame)
                img_b64 = base64.b64encode(jpg_buf).decode('utf-8')
                
                vision_payload = {
                    "model": self.ollama_vision_model,
                    "messages": [
                        {"role": "user", "content": "Describe what you see in this image in detail. Focus on any people, vehicles, safety equipment, or toolboxes.", "images": [img_b64]}
                    ],
                    "stream": False
                }
                # Run the blocking requests.post in an executor to keep the event loop responsive
                loop = asyncio.get_event_loop()
                def post_request():
                    return requests.post(f"{self.ollama_host}/api/chat", json=vision_payload, timeout=30)
                
                vision_res = await loop.run_in_executor(None, post_request)
                if vision_res.status_code == 200:
                    return vision_res.json().get('message', {}).get('content', '').strip()
            except Exception as e:
                logger.warning(f"Ollama captioning failed: {e}")
        else:
            try:
                # Convert cv2 frame (BGR) to PIL image (RGB)
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                response = self.client.models.generate_content(
                    model=MODEL_ID,
                    contents=["Describe what you see in this downward drone camera view. Be specific.", pil_img]
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Google GenAI captioning failed: {e}")
        return "Drone is observing the environment."

    def ensure_camera_view_open(self):
        try:
            logger.info("Ensuring downward depth camera feed is open in Gazebo...")
            env = {"DISPLAY": ":1"}
            
            res_tree = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
            lines = res_tree.stdout.splitlines()
            
            gazebo_win_id = None
            for line in lines:
                if '"Gazebo"' in line:
                    gazebo_win_id = line.split()[0]
                    break
                    
            if not gazebo_win_id:
                logger.warning("No Gazebo main window found. Skipping camera auto-open.")
                return
                
            camera_already_open = False
            for line in lines:
                if '"Image View"' in line or '"Gazebo: Image View"' in line:
                    camera_already_open = True
                    break
                                
            if camera_already_open:
                logger.info("Gazebo camera visualization window is already open.")
                return
                
            dialog_win_id = None
            for line in lines:
                if '"gazebo"' in line and "576x320" in line:
                    m = re.search(r"(0x[0-9a-fA-F]+)", line)
                    if m:
                        dialog_win_id = m.group(1)
                        break

            if not dialog_win_id:
                logger.info("Camera view window not found. Activating Gazebo and triggering Topic Selector...")
                subprocess.run(["xdotool", "windowactivate", gazebo_win_id], env=env)
                time.sleep(1.0)
                
                # Clear menus
                subprocess.run(["xdotool", "mousemove", "900", "500", "click", "1"], env=env)
                time.sleep(0.5)
                
                # Open window menu
                subprocess.run(["xdotool", "mousemove", "220", "78", "click", "1"], env=env)
                time.sleep(0.5)
                
                # Press down and enter
                subprocess.run(["xdotool", "key", "Down"], env=env)
                time.sleep(0.2)
                subprocess.run(["xdotool", "key", "Return"], env=env)
                time.sleep(2.0)
                
                res_tree2 = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
                for line in res_tree2.stdout.splitlines():
                    if '"gazebo"' in line and "576x320" in line:
                        m = re.search(r"(0x[0-9a-fA-F]+)", line)
                        if m:
                            dialog_win_id = m.group(1)
                            break
                        
            if not dialog_win_id:
                logger.warning("Could not locate Topic Selector dialog. Attempting keyboard backup...")
                for _ in range(6):
                    subprocess.run(["xdotool", "key", "Down"], env=env)
                    time.sleep(0.1)
                subprocess.run(["xdotool", "key", "Right"], env=env)
                time.sleep(0.5)
                subprocess.run(["xdotool", "key", "Down"], env=env)
                time.sleep(0.3)
                subprocess.run(["xdotool", "key", "Return"], env=env)
                time.sleep(2.0)
                return
                
            subprocess.run(["xdotool", "mousemove", "--window", dialog_win_id, "15", "148", "click", "1"], env=env)
            time.sleep(1.0)
            subprocess.run(["xdotool", "mousemove", "--window", dialog_win_id, "100", "166", "click", "1"], env=env)
            time.sleep(0.1)
            subprocess.run(["xdotool", "mousemove", "--window", dialog_win_id, "100", "166", "click", "1"], env=env)
            time.sleep(2.0)
            logger.info("Gazebo camera visualization window successfully initialized.")
        except Exception as e:
            logger.error(f"Failed to automatically open Gazebo camera window: {e}")

    async def capture_vision(self):
        self.ensure_camera_view_open()
        raise_gazebo()
        viewport = get_gazebo_viewport()
        # Get actual monitor size to prevent crashes
        main_monitor = self.sct.monitors[0] # Monitor 0 is the composite of all monitors
        
        # Clip viewport to monitor boundaries
        left = max(0, min(viewport[0], main_monitor['width'] - 100))
        top = max(0, min(viewport[1], main_monitor['height'] - 100))
        width = min(viewport[2], main_monitor['width'] - left)
        height = min(viewport[3], main_monitor['height'] - top)
        
        monitor = {"top": top, "left": left, "width": width, "height": height}
        
        try:
            img = np.array(self.sct.grab(monitor))
        except Exception as e:
            logger.error(f"Screenshot failed at {monitor}. Screen size is {main_monitor['width']}x{main_monitor['height']}")
            # Fallback: Capture full primary monitor
            img = np.array(self.sct.grab(self.sct.monitors[1]))
            
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        results = self.yolo.predict(img_bgr, conf=0.3, verbose=False)
        current_detections = []
        for box in results[0].boxes:
            cls = int(box.cls[0])
            name = results[0].names[cls]
            current_detections.append(name)
        
        self.targets = list(set(current_detections))
        self.update_slam_landmarks(self.targets)
        
        # Plot bounding boxes on frame for visualization
        annotated_frame = results[0].plot()
        
        # Show FPV feed with overlay in a local window
        try:
            cv2.namedWindow("Omnia Vision - YOLO Bounding Box Overlay", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Omnia Vision - YOLO Bounding Box Overlay", 640, 360)
            cv2.moveWindow("Omnia Vision - YOLO Bounding Box Overlay", 50, 650)
            cv2.imshow("Omnia Vision - YOLO Bounding Box Overlay", annotated_frame)
            cv2.waitKey(1)
            cv2.imwrite('/tmp/omnia_current_frame.jpg', annotated_frame)
        except Exception as win_err:
            logger.warning(f"Could not render CV2 window: {win_err}")
            
        return img_bgr

    # --- TOOLS ---
    def _send_fifo_cmd(self, cmd_str: str):
        """Dispatches commands via command FIFO, retrying if the controller reader is busy/offline."""
        import time
        start_time = time.time()
        while True:
            try:
                fd = os.open(COMMAND_FIFO, os.O_WRONLY | os.O_NONBLOCK)
                with os.fdopen(fd, 'w') as f:
                    f.write(cmd_str + "\n")
                logger.info(f"Successfully sent command to FIFO: '{cmd_str}'")
                break
            except OSError:
                if time.time() - start_time > 120:
                    logger.error(f"Timeout (120s) waiting to write command to {COMMAND_FIFO}")
                    break
                time.sleep(0.5)

    def move_drone(self, direction: str, distance: float):
        """Move the drone. Directions: F (Forward), B (Backward), L (Left), R (Right)"""
        cmd = f"{direction}{distance}"
        self._send_fifo_cmd(cmd)
        return f"Moving {direction} by {distance}m"

    def land_drone(self):
        """Lands the drone safely."""
        self._send_fifo_cmd("LAND")
        return "Landing protocol initiated."

    def yaw_drone(self, direction: str, angle: float):
        """Rotate the drone. Directions: C (Clockwise), A (Anti-clockwise)"""
        cmd = f"{direction}{angle}"
        self._send_fifo_cmd(cmd)
        return f"Rotating {direction} by {angle} degrees"

    def change_altitude(self, altitude: float):
        """Sets the drone's altitude directly."""
        cmd = f"ALT{altitude}"
        self._send_fifo_cmd(cmd)
        return f"Setting altitude to {altitude}m"

    def send_commands(self, cmds_string: str):
        """Sends multiple space-separated commands to the controller."""
        self._send_fifo_cmd(cmds_string)
        return f"Dispatched commands: {cmds_string}"

    def see_and_report(self):
        """Specialized vision analysis of current view."""
        return f"Currently seeing: {', '.join(self.targets) if self.targets else 'No critical targets identified.'}"

    async def execute_mission_profile_step(self):
        action_type = "UNKNOWN"
        action_data = {}
        scene_description = f"Autonomous flight execution for {self.mission_mode} profile."
        response_text = f"Executing step {self.mission_step} of {self.mission_mode} routine."

        if self.mission_mode == "COURIER":
            if self.mission_step == 0:
                self.mission_phase = "TAKEOFF"
                self.payload_status = "None"
                self.alert_message = "Dispatched Courier Mission: Initiating takeoff to 2.5m..."
                self.send_commands("T2.5 F2.0")
                action_type = "move"
                action_data = {"direction": "UP", "altitude": 2.5}
                self.mission_step = 1
            elif self.mission_step == 1:
                self.mission_phase = "NAVIGATING"
                self.alert_message = "Aligning yaw to Q1 (+45 deg) and flying forward..."
                self.send_commands("C45 F5.0 R5.0")
                action_type = "move"
                action_data = {"direction": "NE", "distance": 7.07}
                self.mission_step = 2
            elif self.mission_step == 2:
                self.mission_phase = "SEARCHING"
                self.alert_message = "Performing active FPV camera search sweep..."
                action_type = "search"
                action_data = {"action": "scan_fpv"}
                if "person" in self.targets:
                    self.alert_message = "CRITICAL: Fallen Casualty Detected in Q1! Person is lying flat."
                    self.add_saved_fact("Fallen person detected lying flat in Quadrant 1.")
                    self.mission_step = 3
                else:
                    self.send_commands("A30 C60 A30")
                    await asyncio.sleep(4)
            elif self.mission_step == 3:
                self.mission_phase = "SECURING CARGO"
                self.payload_status = "Securing Package..."
                self.alert_message = "Descending to 1.0m to engage cargo winch..."
                action_type = "cargo"
                action_data = {"action": "winch_descend"}
                self.change_altitude(1.0)
                await asyncio.sleep(5)
                self.payload_status = "Package Secured"
                self.alert_message = "Cargo secured! Climbing back to 2.5m travel height..."
                self.change_altitude(2.5)
                self.mission_step = 4
            elif self.mission_step == 4:
                self.mission_phase = "RETURNING"
                self.alert_message = "Flying return path to office central pad..."
                self.send_commands("L5.0 B5.0")
                action_type = "move"
                action_data = {"direction": "SW", "distance": 7.07}
                self.mission_step = 5
            elif self.mission_step == 5:
                self.mission_phase = "LANDING"
                self.alert_message = "Resetting yaw and initiating touchdown landing..."
                self.send_commands("A45 LAND")
                action_type = "land"
                action_data = {"action": "land"}
                self.mission_step = 6
            elif self.mission_step == 6:
                self.mission_phase = "COMPLETED"
                self.alert_message = "Courier Delivery Completed Successfully!"
                action_type = "completed"
                action_data = {"action": "completed"}
                self.mission_mode = None

        elif self.mission_mode == "SAR_RESCUE":
            if self.mission_step == 0:
                self.mission_phase = "TAKEOFF"
                self.payload_status = "Life Jacket Loaded"
                self.alert_message = "Dispatched Search & Rescue: Takeoff to 2.5m..."
                self.send_commands("T2.5 F2.0")
                action_type = "move"
                action_data = {"direction": "UP", "altitude": 2.5}
                self.mission_step = 1
            elif self.mission_step == 1:
                self.mission_phase = "NAVIGATING"
                self.alert_message = "Aligning yaw to Q2 (+135 deg) and flying forward..."
                self.send_commands("C135 B5.0 R5.0")
                action_type = "move"
                action_data = {"direction": "SE", "distance": 7.07}
                self.mission_step = 2
            elif self.mission_step == 2:
                self.mission_phase = "SEARCHING"
                self.alert_message = "Performing active FPV camera search sweep..."
                action_type = "search"
                action_data = {"action": "scan_fpv"}
                if "red toolbox" in self.targets:
                    self.alert_message = "Target Located: Red Box Identified in Q2!"
                    self.add_saved_fact("Red box located in Quadrant 2 warehouse.")
                    self.mission_step = 3
                else:
                    self.send_commands("A30 C60 A30")
                    await asyncio.sleep(4)
            elif self.mission_step == 3:
                self.mission_phase = "LOCK-ON"
                self.alert_message = "Lock-on established. Descending to 1.0m altitude..."
                action_type = "lockon"
                action_data = {"action": "descend"}
                self.change_altitude(1.0)
                self.mission_step = 4
            elif self.mission_step == 4:
                self.mission_phase = "RESCUING"
                self.payload_status = "Dropping Life Jacket..."
                self.alert_message = "DEPLOYING LIFE JACKET / SURVIVAL AID!"
                action_type = "cargo"
                action_data = {"action": "drop_aid"}
                await asyncio.sleep(5)
                self.payload_status = "Life Jacket Deployed"
                self.alert_message = "Survival gear dropped! Climbing back to 2.5m..."
                self.change_altitude(2.5)
                self.mission_step = 5
            elif self.mission_step == 5:
                self.mission_phase = "RETURNING"
                self.alert_message = "Flying return path to base central pad..."
                self.send_commands("L5.0 F5.0")
                action_type = "move"
                action_data = {"direction": "NW", "distance": 7.07}
                self.mission_step = 6
            elif self.mission_step == 6:
                self.mission_phase = "LANDING"
                self.alert_message = "Resetting yaw and initiating touchdown landing..."
                self.send_commands("A135 LAND")
                action_type = "land"
                action_data = {"action": "land"}
                self.mission_step = 7
            elif self.mission_step == 7:
                self.mission_phase = "COMPLETED"
                self.alert_message = "Search & Rescue Mission Completed!"
                action_type = "completed"
                action_data = {"action": "completed"}
                self.mission_mode = None

        elif self.mission_mode == "MEDICAL":
            if self.mission_step == 0:
                self.mission_phase = "TAKEOFF"
                self.payload_status = "Medical Supplies Loaded"
                self.alert_message = "Dispatched Emergency Medical: Takeoff to 2.5m..."
                self.send_commands("T2.5 F2.0")
                action_type = "move"
                action_data = {"direction": "UP", "altitude": 2.5}
                self.mission_step = 1
            elif self.mission_step == 1:
                self.mission_phase = "NAVIGATING"
                self.alert_message = "Aligning yaw to Q3 (-135 deg) and flying forward..."
                self.send_commands("A135 B5.0 L5.0")
                action_type = "move"
                action_data = {"direction": "SW", "distance": 7.07}
                self.mission_step = 2
            elif self.mission_step == 2:
                self.mission_phase = "SCANNING SAFE PAD"
                self.alert_message = "Performing active FPV camera search sweep..."
                action_type = "search"
                action_data = {"action": "scan_fpv"}
                if "person" in self.targets:
                    self.alert_message = "CRITICAL: Drowning Person Detected in Q3 Flooded Area!"
                    self.add_saved_fact("Drowning person detected in Quadrant 3 flood zone.")
                    self.mission_step = 3
                else:
                    self.send_commands("A30 C60 A30")
                    await asyncio.sleep(4)
            elif self.mission_step == 3:
                self.mission_phase = "LOCK-ON"
                self.alert_message = "Lock-on established. Descending to 1.0m altitude..."
                action_type = "lockon"
                action_data = {"action": "descend"}
                self.change_altitude(1.0)
                self.mission_step = 4
            elif self.mission_step == 4:
                self.mission_phase = "DELIVERING"
                self.payload_status = "Releasing Medical Supplies..."
                self.alert_message = "DELIVERING EMERGENCY MEDICAL AID!"
                action_type = "cargo"
                action_data = {"action": "drop_aid"}
                await asyncio.sleep(5)
                self.payload_status = "Medical Supplies Delivered"
                self.alert_message = "Supplies released! Climbing back to 2.5m..."
                self.change_altitude(2.5)
                self.mission_step = 5
            elif self.mission_step == 5:
                self.mission_phase = "RETURNING"
                self.alert_message = "Flying return path to hospital base central pad..."
                self.send_commands("R5.0 F5.0")
                action_type = "move"
                action_data = {"direction": "NE", "distance": 7.07}
                self.mission_step = 6
            elif self.mission_step == 6:
                self.mission_phase = "LANDING"
                self.alert_message = "Resetting yaw and initiating touchdown landing..."
                self.send_commands("C135 LAND")
                action_type = "land"
                action_data = {"action": "land"}
                self.mission_step = 7
            elif self.mission_step == 7:
                self.mission_phase = "COMPLETED"
                self.alert_message = "Medical Delivery Mission Completed!"
                action_type = "completed"
                action_data = {"action": "completed"}
                self.mission_mode = None

        return action_type, action_data, scene_description, response_text

    async def run_loop(self):
        logger.info("Omnia Agentic Pilot (Pseudo-Live Mode) is online.")
        logger.info("Using standard API to reach mission goals...")
        
        while True:
            # Reload memory file
            self.load_memory()

            # Check for active mission selection
            mission_file = "/tmp/omnia_active_mission.json"
            if os.path.exists(mission_file):
                try:
                    with open(mission_file, 'r') as f:
                        m_data = json.load(f)
                    if m_data.get("command") == "START":
                        self.mission_mode = m_data.get("mission")
                        self.mission_phase = "TAKEOFF"
                        self.mission_step = 0
                        self.alert_message = f"Dispatched {self.mission_mode} Mission"
                        try: os.remove(mission_file)
                        except Exception: pass
                    elif m_data.get("command") == "ABORT":
                        self.mission_mode = None
                        self.mission_phase = "ABORTING"
                        self.alert_message = "MISSION ABORTED. Landing drone."
                        self.land_drone()
                        try: os.remove(mission_file)
                        except Exception: pass
                except Exception as mis_err:
                    logger.warning(f"Could not read active mission file: {mis_err}")

            # Check for dynamic user instruction
            user_instruction = ""
            instruction_file = "/tmp/omnia_user_instruction.json"
            if os.path.exists(instruction_file):
                try:
                    with open(instruction_file, 'r') as f:
                        data = json.load(f)
                    if not data.get("processed", False):
                        user_instruction = data.get("instruction", "")
                        data["processed"] = True
                        with open(instruction_file, 'w') as f:
                            json.dump(data, f)
                        logger.info(f"Received dynamic user instruction: {user_instruction}")
                        
                        # Add command to memory history
                        if "commands_history" not in self.memory:
                            self.memory["commands_history"] = []
                        self.memory["commands_history"].append({
                            "instruction": user_instruction,
                            "timestamp": datetime.now().isoformat()
                        })
                        self.save_memory()
                except Exception as instr_err:
                    logger.warning(f"Could not read user instruction: {instr_err}")

            await self.get_telemetry()

            # Update cooperative multi-drone registry in shared memory
            try:
                self.load_memory()
                if "active_drones" not in self.memory:
                    self.memory["active_drones"] = {}
                self.memory["active_drones"][self.drone_id] = {
                    "latitude": self.telemetry.get("latitude", 0),
                    "longitude": self.telemetry.get("longitude", 0),
                    "altitude": self.telemetry.get("altitude", 0),
                    "bearing": self.telemetry.get("bearing", 0),
                    "status": self.mission_mode if self.mission_mode else "IDLE",
                    "phase": self.mission_phase,
                    "last_update": time.time(),
                    "trajectory": self.history
                }
                self.save_memory()
            except Exception as active_drones_err:
                logger.warning(f"Could not update active_drones registry: {active_drones_err}")

            # Query the RAG system
            rag_query = user_instruction if user_instruction else (self.mission_mode if self.mission_mode else "cruising altitude safety")
            retrieved_sop = self.rag.retrieve(rag_query, top_k=2)
            
            sop_section = ""
            if retrieved_sop:
                sop_section += "\n=== RETRIEVED STANDARD OPERATING PROCEDURES (SOP) ===\n"
                for chunk in retrieved_sop:
                    sop_section += f"{chunk}\n"
                sop_section += "=====================================================\n"

            # Build memory system prompt injection
            memories_section = ""
            if hasattr(self, 'memory') and self.memory:
                memories_section += "\n=== ACTIVE PILOT MEMORY & ENVIRONMENT KNOWLEDGE ===\n"
                memories_section += "GEOSPATIAL QUADRANTS:\n"
                for q, desc in self.memory.get("quadrants", {}).items():
                    memories_section += f"- {q}: {desc}\n"
                memories_section += "\nPRE-LOADED LOCATIONS:\n"
                for loc, coords in self.memory.get("locations", {}).items():
                    memories_section += f"- {loc.upper()}: X={coords['x']}, Y={coords['y']}\n"
                memories_section += "\nSAVED FACTS & USER OPERATOR MEMORIES:\n"
                for fact in self.memory.get("saved_facts", []):
                    memories_section += f"- {fact}\n"
                memories_section += "=================================================\n"

            system_prompt = f"""
            You are the 'Omnia' Search and Rescue Pilot.
            MISSION: Assist first responders by finding targets (person, toolbox, vest, car) in the warehouse.
            DATA: Telemetry={self.telemetry}. Detections={self.targets}.
            COMMANDS AVAILABLE: move_drone, land_drone, see_and_report.
            {memories_section}
            {sop_section}
            """
            
            if user_instruction:
                system_prompt += f"\nCRITICAL OPERATOR DIRECTIVE: {user_instruction}\nYou MUST prioritize this dynamic directive above other exploratory behaviors."

            lat = self.telemetry.get("latitude", 0)
            lon = self.telemetry.get("longitude", 0)
            if lat != 0 or lon != 0:
                if len(self.history) > 500:
                    self.history.pop(0)
                self.history.append({
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": self.telemetry.get("altitude", 0),
                    "bearing": self.telemetry.get("bearing", 0),
                    "timestamp": time.time()
                })
            
            frame = await self.capture_vision()
            
            # Continuous VLM captioning for ReMEmbR memory database building
            scene_description = "Drone is hovering and observing."
            try:
                scene_description = await self.caption_frame(frame)
                logger.info(f"🧠 ReMEmbR memory builder captioned: {scene_description}")
                self.remembr_store_observation(scene_description, self.targets)
            except Exception as vlm_err:
                logger.warning(f"VLM continuous captioning failed: {vlm_err}")
            
            try:
                pre_telemetry = dict(self.telemetry)
                pre_targets = list(self.targets)

                action_type = "hover"
                action_data = {}
                response_text = "Observing environment."

                # --- Handle Operator Navigation and Memory Commands directly ---
                if user_instruction:
                    cleaned_instr = user_instruction.lower().strip()
                    
                    # 1. Check for ReMEmbR Semantic Memory Queries ("where did you see X", "where was the Y", "find Z")
                    if any(word in cleaned_instr for word in ["where did you see", "where was the", "find the", "find a"]):
                        query_term = user_instruction
                        for prefix in ["where did you see the", "where did you see a", "where did you see", "where was the", "where was a", "find the", "find a", "find"]:
                            if cleaned_instr.startswith(prefix):
                                query_term = user_instruction[len(prefix):].strip()
                                break
                        # Run a combined vector semantic/spatial query
                        results = self.remembr.query_by_text(query_term, top_k=3)
                        if results:
                            top_mem, score = results[0]
                            t_ago = (time.time() - top_mem['timestamp']) / 60
                            response_text = f"I remember seeing '{top_mem['caption']}' at local coordinates X={top_mem['local_xy']['x']:.1f}, Y={top_mem['local_xy']['y']:.1f} ({t_ago:.1f} minutes ago) with match confidence {score:.2f}."
                            self.alert_message = f"Found memory: {top_mem['caption'][:40]}"
                            # If they also said "go" or "fly" or "navigate", fly there!
                            if any(word in cleaned_instr for word in ["go", "fly", "navigate", "return"]):
                                remembr_result = self.remembr_navigate_to(query_term)
                                if remembr_result:
                                    self.mission_mode = None
                                    self.mission_phase = "COORDINATE NAV"
                                    action_type = "coordinate_nav"
                                    action_data = {"target": query_term, "source": "remembr"}
                                    response_text += f"\n{remembr_result}"
                        else:
                            response_text = f"I don't have any visual memories matching '{query_term}'."
                            self.alert_message = "No matching memories."
                        action_type = "query_memory"
                        action_data = {"query": query_term}
                        user_instruction = ""
                    
                    # 2. Check if it is a nav command to a landmark or remembered object
                    elif any(word in cleaned_instr for word in ["go to", "fly to", "navigate to", "go back to", "return to"]):
                        # Extract the target search query
                        search_query = user_instruction
                        for prefix in ["go to the", "go back to the", "fly to the", "navigate to the", "go to", "go back to", "fly to", "navigate to", "return to"]:
                            if cleaned_instr.startswith(prefix):
                                search_query = user_instruction[len(prefix):].strip()
                                break
                        
                        # First try ReMEmbR semantic vector navigation
                        remembr_result = self.remembr_navigate_to(search_query)
                        if remembr_result:
                            self.mission_mode = None
                            self.mission_phase = "COORDINATE NAV"
                            action_type = "coordinate_nav"
                            action_data = {"target": search_query, "source": "remembr"}
                            response_text = remembr_result
                            self.add_saved_fact(f"ReMEmbR navigation to: {search_query}")
                            user_instruction = ""
                        else:
                            # Fallback to standard SLAM landmark names
                            target_landmark = None
                            possible_targets = {
                                "car": "blue car", "blue car": "blue car",
                                "toolbox": "red toolbox", "red toolbox": "red toolbox",
                                "person": "person", "casualty": "person",
                                "vest": "safety vest", "safety vest": "safety vest"
                            }
                            for kw, target_name in possible_targets.items():
                                if kw in search_query.lower():
                                    target_landmark = target_name
                                    break
                            
                            if target_landmark:
                                self.mission_mode = None
                                self.mission_phase = "COORDINATE NAV"
                                self.load_memory()
                                detected = self.memory.get("detected_landmarks", {}).get(target_landmark)
                                if detected:
                                    target_x = detected["x"]
                                    target_y = detected["y"]
                                    self.alert_message = f"SLAM Navigation: Flying to dynamically detected {target_landmark} at X={target_x}, Y={target_y}..."
                                    res = self.navigate_to_local_xy(target_x, target_y)
                                    action_type = "coordinate_nav"
                                    action_data = {"target": target_landmark, "x": target_x, "y": target_y}
                                    response_text = f"Dynamic SLAM navigation executed: {res}"
                                    self.add_saved_fact(f"Navigating to dynamically mapped {target_landmark} at X={target_x}, Y={target_y}.")
                                else:
                                    # Fallback to RAG
                                    fallback_x, fallback_y = None, None
                                    for q, desc in self.memory.get("quadrants", {}).items():
                                        if target_landmark in desc.lower() or (target_landmark == "blue car" and "car" in desc.lower()):
                                            m_coord = re.search(r"Location:\s*X=([+-]?\d+\.?\d*),\s*Y=([+-]?\d+\.?\d*)", desc)
                                            if m_coord:
                                                fallback_x = float(m_coord.group(1))
                                                fallback_y = float(m_coord.group(2))
                                                self.alert_message = f"RAG Navigation: {target_landmark} not yet mapped. Flying to default location (X={fallback_x}, Y={fallback_y})..."
                                                break
                                    if fallback_x is not None and fallback_y is not None:
                                        res = self.navigate_to_local_xy(fallback_x, fallback_y)
                                        action_type = "coordinate_nav"
                                        action_data = {"target": target_landmark, "x": fallback_x, "y": fallback_y}
                                        response_text = f"RAG-based navigation executed: {res}"
                                    else:
                                        response_text = f"Target '{target_landmark}' is not yet detected by SLAM and no default coordinates were found in memory."
                                        self.alert_message = f"Error: Cannot navigate to '{target_landmark}'."
                            else:
                                response_text = f"Could not find any memories or landmark mappings matching '{search_query}'."
                                self.alert_message = f"Error: Cannot find '{search_query}'."
                            user_instruction = ""
                    
                    # 3. Rest of manual navigation / facts storage overrides
                    elif "home" in cleaned_instr and ("go" in cleaned_instr or "fly" in cleaned_instr or "navigate" in cleaned_instr):
                        self.mission_mode = None
                        self.mission_phase = "COORDINATE NAV"
                        self.alert_message = "Operator Override: Navigating directly to Home building (Q4)..."
                        res = self.navigate_to_local_xy(4.0, -4.0)
                        action_type = "coordinate_nav"
                        action_data = {"target": "home", "x": 4.0, "y": -4.0}
                        response_text = f"Direct navigation override executed: {res}"
                        self.add_saved_fact("Operator ordered flight to Home building at X=4.0, Y=-4.0.")
                        user_instruction = ""
                    elif "hospital" in cleaned_instr and ("go" in cleaned_instr or "fly" in cleaned_instr or "navigate" in cleaned_instr):
                        self.mission_mode = None
                        self.mission_phase = "COORDINATE NAV"
                        self.alert_message = "Operator Override: Navigating directly to Hospital building (Q4)..."
                        res = self.navigate_to_local_xy(6.0, -6.0)
                        action_type = "coordinate_nav"
                        action_data = {"target": "hospital", "x": 6.0, "y": -6.0}
                        response_text = f"Direct navigation override executed: {res}"
                        self.add_saved_fact("Operator ordered flight to Hospital building at X=6.0, Y=-6.0.")
                        user_instruction = ""
                    elif ("origin" in cleaned_instr or "base" in cleaned_instr or "start" in cleaned_instr) and ("go" in cleaned_instr or "fly" in cleaned_instr or "navigate" in cleaned_instr):
                        self.mission_mode = None
                        self.mission_phase = "COORDINATE NAV"
                        self.alert_message = "Operator Override: Returning to Central Launch Pad..."
                        res = self.navigate_to_local_xy(0.0, 0.0)
                        action_type = "coordinate_nav"
                        action_data = {"target": "origin", "x": 0.0, "y": 0.0}
                        response_text = f"Direct navigation override executed: {res}"
                        self.add_saved_fact("Operator ordered flight back to Central origin pad.")
                        user_instruction = ""
                    elif "remember" in cleaned_instr or "store" in cleaned_instr:
                        fact_to_save = user_instruction
                        for prefix in ["remember that", "remember", "store that", "store"]:
                            if cleaned_instr.startswith(prefix):
                                fact_to_save = user_instruction[len(prefix):].strip()
                                break
                        self.add_saved_fact(fact_to_save)
                        self.alert_message = f"New Fact Saved to Memory: '{fact_to_save}'"
                        action_type = "save_memory"
                        action_data = {"fact": fact_to_save}
                        response_text = f"Saved '{fact_to_save}' to pilot memory file."
                        user_instruction = ""

                # --- Normal Mission Step or LLM Decision Loop ---
                if self.mission_mode is not None:
                    action_type, action_data, _, response_text = await self.execute_mission_profile_step()
                elif user_instruction: # General LLM reasoning if query command didn't match directly
                    if self.use_ollama:
                        import requests
                        # Reason with text model using already generated scene_description
                        action_prompt = f"{system_prompt}\n\nVISION REPORT: {scene_description}\nYOLO DETECTIONS: {self.targets}\n\nBased on the above, what is your next action? Output ONLY valid JSON: {{\"action\": \"move\", \"direction\": \"F\", \"distance\": 2}} or {{\"action\": \"land\"}}."
                        action_payload = {
                            "model": self.ollama_model,
                            "messages": [
                                {"role": "user", "content": action_prompt}
                            ],
                            "stream": False,
                            "format": "json"
                        }
                        action_res = requests.post(f"{self.ollama_host}/api/chat", json=action_payload, timeout=30)
                        if action_res.status_code == 200:
                            response_text = action_res.json().get('message', {}).get('content', '')
                            try:
                                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                                if json_match:
                                    action_data = json.loads(json_match.group(0))
                                    action_type = action_data.get('action', 'UNKNOWN')
                                    if action_type in ('move', 'move_drone'):
                                        self.move_drone(action_data['direction'], action_data['distance'])
                                    elif action_type in ('land', 'land_drone'):
                                        self.land_drone()
                            except Exception as parse_err:
                                logger.warning(f"Failed parsing Ollama instruction response: {parse_err}")
                        else:
                            logger.error(f"Ollama text model failed: {action_res.status_code}")
                
                # Format and output the OMNIA Agent ReAct Trace
                react_log = (
                    f"{'='*55}\n"
                    f"📡 TELEMETRY   : {self.telemetry}\n"
                    f"👁️ DETECTIONS   : {self.targets}\n"
                    f"📖 SCENE REPORT : {scene_description.strip() if 'scene_description' in locals() else 'N/A'}\n"
                    f"🧠 THINKING     : {response_text.strip()}\n"
                    f"⚙️ EXECUTED     : {action_type.upper()} ({action_data if action_type != 'land' else 'LAND'})\n"
                    f"{'='*55}"
                )
                logger.info(react_log)

                # Write state for the web dashboard (includes memories!)
                try:
                    dashboard_state = {
                        "telemetry": self.telemetry,
                        "detections": self.targets,
                        "scene_description": scene_description.strip() if 'scene_description' in locals() else 'N/A',
                        "thinking": response_text.strip() if 'response_text' in locals() else 'N/A',
                        "action": action_type,
                        "action_data": action_data,
                        "history": self.history,
                        "mission_mode": self.mission_mode,
                        "mission_phase": self.mission_phase,
                        "payload_status": self.payload_status,
                        "alert_message": self.alert_message,
                        "memories": self.memory,
                        "retrieved_sop": retrieved_sop,
                        "remembr_memories": self.remembr.memories,
                        "remembr_summary": self.remembr.get_memory_summary()
                    }
                    with open('/tmp/omnia_dashboard_state.json', 'w') as f:
                        json.dump(dashboard_state, f)
                except Exception as dash_err:
                    logger.warning(f"Could not update dashboard state: {dash_err}")

                # Trigger Reflection and Learning loop
                if action_type != "hover":
                    await self.reflect_on_step(action_type, action_data, pre_telemetry, pre_targets)

            except Exception as e:
                logger.error(f"Loop Error: {e}")
            
            await asyncio.sleep(10) # Protect your free tier quota

if __name__ == "__main__":
    pilot = OmniaPilotPseudoLive()
    asyncio.run(pilot.run_loop())
