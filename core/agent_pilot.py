import asyncio
import os
import cv2
import numpy as np
import mss
import logging
import base64
from ultralytics import YOLOWorld
from google import genai
from google.genai import types
from drone_controller import DroneController
from dotenv import load_dotenv

load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OmniaPilot")

# CONFIGURATION
MODEL_ID = "gemini-2.0-flash-exp"  # Or your preferred Gemini 2.0 version
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class OmniaPilot:
    def __init__(self):
        self.controller = DroneController()
        self.yolo = YOLOWorld('yolov8s-world.pt')
        self.yolo.set_classes(["person", "reflective vest", "red toolbox", "unauthorized vehicle"])
        
        self.client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
        self.sct = mss.mss()
        
    async def capture_screen(self):
        # Captures the Gazebo window area - adjust coordinates as needed
        # monitor = {"top": 100, "left": 100, "width": 800, "height": 600}
        monitor = self.sct.monitors[1] # Capture primary monitor by default
        sct_img = self.sct.grab(monitor)
        img = np.array(sct_img)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        return img

    def process_vision(self, frame):
        results = self.yolo.predict(frame, verbose=False, device='0')
        detections = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                label = result.names[cls]
                conf = float(box.conf[0])
                # Normalized coordinates
                x1, y1, x2, y2 = box.xyxyn[0].tolist()
                detections.append(f"{label} (conf: {conf:.2f}) at [{x1:.2f}, {y1:.2f}, {x2:.2f}, {y2:.2f}]")
        return detections

    async def run(self):
        # 1. Connect to Drone
        # await self.controller.connect() # Uncomment when SITL is running

        # 2. Define Live API Tools
        tools = [
            self.controller.arm_and_takeoff,
            self.controller.land,
            self.controller.goto_location,
            self.controller.get_telemetry
        ]

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=tools,
            system_instruction=types.Content(
                parts=[types.Part(text="""You are Omnia-Pilot, a Semantic First Responder drone. 
You listen to voice commands and 'see' through a real-time vision feed.
Your goal is to autonomously search for targets, identify safety risks, and aid in emergency operations.
If the user asks you to find something, use your vision feed and local YOLO detections to locate it.
You have tools to control the drone. Use them wisely.
Maintain a professional, helpful, and urgent demeanor fitting for a First Responder.""")]
            )
        )

        logger.info("Connecting to Gemini Multimodal Live Session...")
        async with self.client.aio.live.connect(model=MODEL_ID, config=config) as session:
            
            async def send_frames():
                while True:
                    frame = await self.capture_screen()
                    detections = self.process_vision(frame)
                    
                    # Convert frame for Gemini (JPEG)
                    _, buffer = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                    frame_bytes = buffer.tobytes()
                    
                    # Send frame with detection metadata as text overlay/part
                    meta_text = "Local Detections: " + (", ".join(detections) if detections else "None")
                    
                    await session.send(input=[
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=frame_bytes)),
                        types.Part(text=meta_text)
                    ], end_of_turn=True)
                    
                    await asyncio.sleep(0.5) # 2 FPS for stability

            async def receive_responses():
                async for message in session.receive():
                    if message.tool_call:
                        for call in message.tool_call.function_calls:
                            logger.info(f"Executing tool call: {call.name}({call.args})")
                            # Simple dynamic dispatch
                            func = getattr(self.controller, call.name)
                            result = await func(**call.args)
                            
                            await session.send_tool_response(
                                function_responses=[types.FunctionResponse(
                                    name=call.name,
                                    id=call.id,
                                    response={"result": result}
                                )]
                            )
                    elif message.server_content and message.server_content.model_turn:
                        # Audio parts are handled by the client automatically if modalities includes AUDIO
                        # But we could log text parts if available
                        parts = message.server_content.model_turn.parts
                        for part in parts:
                            if part.text:
                                logger.info(f"Omnia: {part.text}")

            await asyncio.gather(send_frames(), receive_responses())

if __name__ == "__main__":
    pilot = OmniaPilot()
    try:
        asyncio.run(pilot.run())
    except KeyboardInterrupt:
        logger.info("Omnia-Pilot shutting down.")
