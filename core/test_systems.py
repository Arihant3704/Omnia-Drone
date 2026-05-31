import os
import sys
import json
import time
import asyncio
import cv2
import numpy as np

def run_test_suite():
    print("=" * 60)
    print("      OMNIA SYSTEM VERIFICATION & DIAGNOSTIC SUITE      ")
    print("=" * 60)

    # 1. Test Imports and Environment
    print("\n[TEST 1] Checking Python package imports...")
    try:
        import dronekit
        import pymavlink
        print("  ✓ dronekit and pymavlink imported successfully.")
    except Exception as e:
        print(f"  ✗ Failed to import dronekit/pymavlink: {e}")

    try:
        from google import genai
        print("  ✓ google-genai library imported successfully.")
    except Exception as e:
        print(f"  ✗ Failed to import google-genai: {e}")

    try:
        from ultralytics import YOLOWorld
        print("  ✓ ultralytics (YOLO) imported successfully.")
    except Exception as e:
        print(f"  ✗ Failed to import ultralytics: {e}")

    # 2. Test YOLO-World inference
    print("\n[TEST 2] Loading YOLO-World & testing dummy inference...")
    try:
        yolo = YOLOWorld('yolov8s-world.pt')
        yolo.set_classes(["person", "red toolbox", "safety vest", "blue car"])
        dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
        results = yolo.predict(dummy_img, conf=0.3, verbose=False)
        print("  ✓ YOLO-World loaded and dummy prediction completed successfully.")
    except Exception as e:
        print(f"  ✗ YOLO-World test failed: {e}")

    # 3. Test Gemini API Connection
    print("\n[TEST 3] Testing Gemini API connectivity...")
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("  ✗ GOOGLE_API_KEY is not defined in the environment or .env file.")
    else:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="models/gemini-3.1-flash-lite-preview",
                contents=["Respond with only the word: 'Connected'"]
            )
            print(f"  ✓ Gemini API responded: '{response.text.strip()}'")
        except Exception as e:
            print(f"  ✗ Gemini API call failed: {e}")

    # 4. Test Ollama Local Model
    print("\n[TEST 4] Testing local Ollama connectivity...")
    try:
        import requests
        payload = {
            "model": "qwen2.5:0.5b",
            "messages": [
                {"role": "user", "content": "Respond with a JSON object: {\"status\": \"ok\"}"}
            ],
            "stream": False,
            "format": "json"
        }
        res = requests.post("http://localhost:11434/api/chat", json=payload, timeout=5)
        if res.status_code == 200:
            content = res.json().get('message', {}).get('content', '').strip()
            print(f"  ✓ Local Ollama responded: '{content}'")
        else:
            print(f"  ✗ Ollama responded with status code {res.status_code}")
    except Exception as e:
        print(f"  ✗ Local Ollama connection failed (is server running?): {e}")

    # 5. Test IPC FIFOs
    print("\n[TEST 5] Testing IPC FIFO creation and non-blocking reads/writes...")
    COMMAND_FIFO = '/tmp/gpt_command_fifo'
    STATUS_FIFO = '/tmp/gpt_status_fifo'
    
    # Clean and create
    for path in [COMMAND_FIFO, STATUS_FIFO]:
        if os.path.exists(path):
            os.remove(path)
        os.mkfifo(path)
        print(f"  ✓ Created FIFO: {path}")

    # Write test
    try:
        # Open in RDWR mode so we can write and read without flushing the pipe
        fd = os.open(COMMAND_FIFO, os.O_RDWR | os.O_NONBLOCK)
        os.write(fd, b"F5\n")
        
        # Read back from the same open descriptor
        data = os.read(fd, 100).decode().strip()
        os.close(fd)
        if "F5" in data:
            print("  ✓ IPC FIFO Write and Read back succeeded.")
        else:
            print(f"  ✗ IPC FIFO read mismatch: Expected 'F5', got '{data}'")
    except Exception as e:
        print(f"  ✗ IPC FIFO test failed: {e}")

    print("\n" + "=" * 60)
    print("                 DIAGNOSTICS COMPLETE                   ")
    print("=" * 60)

if __name__ == '__main__':
    run_test_suite()
