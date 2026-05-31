import asyncio
import os
import cv2
import numpy as np
import mss
import logging
import json
from ultralytics import YOLOWorld
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OmniaPilot_Integrated")

# CONFIGURATION
MODEL_ID = "models/gemini-3.1-flash-live-preview"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# FIFO PATHS (from original project)
COMMAND_FIFO = '/tmp/gpt_command_fifo'
STATUS_FIFO = '/tmp/gpt_status_fifo'
# Viewport Capture Region
VIEWPORT = {"top": 238, "left": 1779, "width": 1081, "height": 875}

# Camera parameters (from original balldetector.py)
VFOV = 98.89
HFOV = 114.59

import math
import time
from geopy.distance import geodesic

class OmniaPilotIntegrated:
    def __init__(self):
        self.yolo = YOLOWorld('yolov8s-world.pt')
        self.yolo.set_classes(["person", "red toolbox", "safety vest", "blue car"])
        
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in .env file")
        
        # Diagnostic: Print masked key
        print(f"DEBUG: Loaded API Key: {self.api_key[:5]}...{self.api_key[-5:]}")
        
        self.client = genai.Client(api_key=self.api_key)
        self.sct = mss.mss()
        self.telemetry = {
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "bearing": 0.0
        }

    def calculate_gps(self, nx, ny):
        """Calculate GPS of an object based on normalized screen coordinates [0-1]."""
        lat = self.telemetry.get("latitude", 0)
        lon = self.telemetry.get("longitude", 0)
        alt = self.telemetry.get("altitude", 0)
        bearing = self.telemetry.get("bearing", 0)

        # Angles from center
        angle_x = (nx - 0.5) * HFOV
        angle_y = -(ny - 0.5) * VFOV

        # Distance on ground
        ground_dist = alt * math.tan(math.radians(math.sqrt(angle_x**2 + angle_y**2)))
        rel_bearing = math.degrees(math.atan2(angle_x, angle_y))
        obj_bearing = (bearing + rel_bearing) % 360

        origin = (lat, lon)
        dest = geodesic(meters=ground_dist).destination(origin, obj_bearing)
        return dest.latitude, dest.longitude

    async def capture_viewport(self):
        sct_img = self.sct.grab(VIEWPORT)
        img = np.array(sct_img)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) # OpenCV format
        return img

    def run_local_vision(self, frame):
        results = self.yolo.predict(frame, verbose=False, device='0', conf=0.25)
        detections = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                label = result.names[cls]
                conf = float(box.conf[0])
                # Normalized coordinates
                nx = (box.xyxyn[0][0] + box.xyxyn[0][2]) / 2
                ny = (box.xyxyn[0][1] + box.xyxyn[0][3]) / 2
                
                obj_lat, obj_lon = self.calculate_gps(nx, ny)
                detections.append(f"{label} at GPS({obj_lat:.6f}, {obj_lon:.6f})")
        return detections

    async def read_telemetry(self):
        """Non-blocking read from the existing status FIFO."""
        while True:
            if os.path.exists(STATUS_FIFO):
                try:
                    with open(STATUS_FIFO, 'r') as fifo:
                        line = fifo.readline().strip()
                        if line:
                            self.telemetry = json.loads(line)
                except Exception as e:
                    logger.debug(f"Telemetry read error: {e}")
            await asyncio.sleep(0.1)

    async def send_command(self, cmd_string):
        """Write commands to the existing controller FIFO."""
        if os.path.exists(COMMAND_FIFO):
            try:
                with open(COMMAND_FIFO, 'w') as fifo:
                    fifo.write(cmd_string + "\n")
                logger.info(f"Command Sent: {cmd_string}")
            except Exception as e:
                logger.error(f"Command send error: {e}")

    # TOOLS for Gemini to call
    async def drone_action(self, instruction: str):
        """Executes a legacy drone command (e.g. 'T10', 'F5', 'LAND')."""
        await self.send_command(instruction)
        return f"Instruction '{instruction}' sent to controller."

    async def move_to(self, lat: float, lon: float):
        """Fly to specific GPS coordinates."""
        cmd = f"GOTO({lat},{lon})"
        await self.send_command(cmd)
        return f"Moving to GPS: {lat}, {lon}"

    async def see_and_report(self, context: str):
        """Triggers a high-fidelity geolocated report of the current scene."""
        frame = await self.capture_viewport()
        detections = self.run_local_vision(frame)
        report = "Current Vision Report:\n" + ("\n".join(detections) if detections else "No targets identified.")
        return report

    async def orbit_at_location(self, lat: float, lon: float, radius: float = 10.0):
        """Orbit a specific GPS location for surveillance."""
        await self.move_to(lat, lon)
        cmd = f"CIRC({radius},1.0,1,true)" 
        await self.send_command(cmd)
        return f"Initiating surveillance orbit at GPS({lat}, {lon}) with {radius}m radius."

    async def generate_emergency_report(self, target_description: str, lat: float, lon: float):
        """Generate a formal mission report for identified survivors or hazards."""
        report = {
            "mission": "Semantic First Responder",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target": target_description,
            "location": {"lat": lat, "lon": lon},
            "status": "Target identified and geolocated."
        }
        with open("mission_report.json", "a") as f:
            f.write(json.dumps(report) + "\n")
        logger.info(f"REPORT SAVED: {target_description} at {lat}, {lon}")
        return "Emergency report generated and saved to mission_report.json"

    async def run(self):
        # Tools defined for the Gemini session
        tools = [self.drone_action, self.move_to, self.see_and_report, self.orbit_at_location, self.generate_emergency_report]

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=tools,
            system_instruction=types.Content(
                parts=[types.Part(text="""You are the Omnia-Pilot Search & Rescue Agent.
You are integrated into a ROS-based drone environment.
You receive a real-time vision feed and local YOLO detections.
Your available commands are:
- T[alt]: Takeoff (e.g. T10)
- F[dist], B[dist], L[dist], R[dist]: Move (e.g. F5 for 5m forward)
- LAND: Land the drone
- RTL: Return to launch
- C[angle], A[angle]: Yaw right/left
- move_to(lat, lon): Go to GPS coordinates.

Coordinate finding with the local detections to pinpoint targets.
If you see a 'red toolbox' or 'person', report it via voice and suggest the next move.""")]
            )
        )

        logger.info("Connecting to Gemini Live Session (Integrated Mode)...")
        async with self.client.aio.live.connect(model=MODEL_ID, config=config) as session:
            
            # Start background telemetry task
            asyncio.create_task(self.read_telemetry())

            async def stream_vision():
                while True:
                    frame = await self.capture_viewport()
                    detections = self.run_local_vision(frame)
                    
                    # Encode for Gemini
                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_bytes = buffer.tobytes()
                    
                    # Construct message with telemetry context
                    tel_text = f"Status: {json.dumps(self.telemetry)}"
                    det_text = "Detections: " + (", ".join(detections) if detections else "None")
                    
                    await session.send(input=[
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=frame_bytes)),
                        types.Part(text=f"{tel_text}\n{det_text}")
                    ], end_of_turn=True)
                    
                    await asyncio.sleep(0.5)

            async def handle_responses():
                async for message in session.receive():
                    if message.tool_call:
                        for call in message.tool_call.function_calls:
                            func = getattr(self, call.name)
                            result = await func(**call.args)
                            await session.send_tool_response(
                                function_responses=[types.FunctionResponse(
                                    name=call.name, id=call.id, response={"result": result}
                                )]
                            )
                    elif message.server_content and message.server_content.model_turn:
                        for part in message.server_content.model_turn.parts:
                            if part.text: logger.info(f"Omnia: {part.text}")

            await asyncio.gather(stream_vision(), handle_responses())

if __name__ == "__main__":
    pilot = OmniaPilotIntegrated()
    try:
        asyncio.run(pilot.run())
    except KeyboardInterrupt:
        logger.info("Integrated Pilot shutting down.")
