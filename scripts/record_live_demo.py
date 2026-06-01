import os
import time
import subprocess
import json
import signal
import re

def get_window_id(name_pattern):
    try:
        # Search visible windows
        output = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--name", name_pattern]).decode().strip()
        ids = output.split()
        if ids:
            return ids[0]
    except Exception:
        pass
    
    # Try searching by class
    try:
        output = subprocess.check_output(["xdotool", "search", "--class", name_pattern.lower()]).decode().strip()
        ids = output.split()
        if ids:
            return ids[0]
    except Exception:
        pass
        
    return None

def arrange_windows():
    print("Arranging windows side-by-side on DISPLAY=:1...")
    os.environ["DISPLAY"] = ":1"
    
    chrome_id = get_window_id("Google-chrome") or get_window_id("Omnia") or get_window_id("Chrome")
    gazebo_id = get_window_id("gazebo") or get_window_id("Gazebo")
    
    if chrome_id:
        print(f"Found Google Chrome window: {chrome_id}")
        subprocess.call(["xdotool", "windowactivate", chrome_id])
        subprocess.call(["xdotool", "windowmove", chrome_id, "0", "0"])
        subprocess.call(["xdotool", "windowsize", chrome_id, "960", "1080"])
    else:
        print("Warning: Google Chrome window not found!")
        
    if gazebo_id:
        print(f"Found Gazebo window: {gazebo_id}")
        subprocess.call(["xdotool", "windowactivate", gazebo_id])
        subprocess.call(["xdotool", "windowmove", gazebo_id, "960", "0"])
        subprocess.call(["xdotool", "windowsize", gazebo_id, "960", "1080"])
    else:
        print("Warning: Gazebo window not found!")

def record_live_flight():
    os.environ["DISPLAY"] = ":1"
    video_dir = "/home/arihant/simulation/demo_videos"
    video_path = os.path.join(video_dir, "drony_dynamic_remembr.mp4")
    
    if os.path.exists(video_path):
        os.remove(video_path)
        
    arrange_windows()
    time.sleep(2)
    
    print("\n1. Starting ffmpeg screen capture...")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "x11grab",
        "-video_size", "1920x1080",
        "-framerate", "30",
        "-i", ":1.0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        video_path
    ]
    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(3)
    
    try:
        # Trigger COURIER mission (causes takeoff and flying to Q1 to search for casualty)
        print("\n2. Triggering Autonomous COURIER Mission...")
        mission_payload = {
            "mission": "COURIER",
            "command": "START",
            "timestamp": time.time()
        }
        with open("/tmp/omnia_active_mission.json", "w") as f:
            json.dump(mission_payload, f)
            
        print("   Mission dispatched! Waiting for takeoff and visual search in Q1...")
        # Wait for takeoff, navigation, and visual captioning/remembrance of targets
        # Let's poll /tmp/omnia_pilot.log to check when a casualty is stored or target is located
        start_time = time.time()
        casualty_found = False
        
        while time.time() - start_time < 90:
            time.sleep(3)
            # Read remembr db to check if memories were written
            remembr_db_path = "/tmp/omnia_remembr.json"
            if os.path.exists(remembr_db_path):
                try:
                    with open(remembr_db_path, "r") as f:
                        db = json.load(f)
                    memories = db.get("memories", [])
                    print(f"   [Telemetry] Active Memories Count: {len(memories)}")
                    
                    # Look for casualty/person/hardhat caption
                    for m in memories:
                        caption = m.get("caption", "").lower()
                        if "person" in caption or "worker" in caption or "casualty" in caption:
                            print(f"   [ReMEmbR] Dynamic Memory Stored: '{m['caption']}' at XY=({m['local_xy']['x']:.1f}, {m['local_xy']['y']:.1f})")
                            casualty_found = True
                            break
                except Exception:
                    pass
            
            if casualty_found:
                break
                
        # Wait a few more seconds to settle
        time.sleep(5)
        
        def send_instruction_and_wait(instruction, wait_after_processing=10):
            instruction_file = "/tmp/omnia_user_instruction.json"
            payload = {
                "instruction": instruction,
                "timestamp": time.time(),
                "processed": False
            }
            with open(instruction_file, "w") as f:
                json.dump(payload, f)
            
            print(f"   Instruction '{instruction}' written. Waiting for pilot to process...")
            instr_start = time.time()
            processed = False
            while time.time() - instr_start < 30:
                time.sleep(1)
                if os.path.exists(instruction_file):
                    try:
                        with open(instruction_file, "r") as f:
                            data = json.load(f)
                        if data.get("processed", False):
                            processed = True
                            break
                    except Exception:
                        pass
            
            if processed:
                print(f"   Pilot processed instruction successfully. Sleeping {wait_after_processing}s for drone actions...")
            else:
                print("   Warning: Instruction processing timed out!")
            time.sleep(wait_after_processing)

        print("\n3. Sending Semantic Search Navigation Query: 'fly to where you saw the person'...")
        send_instruction_and_wait("fly to where you saw the person", wait_after_processing=20)
        
        print("\n4. Sending second query to confirm ReMEmbR memory search: 'where did you see the person'...")
        send_instruction_and_wait("where did you see the person", wait_after_processing=8)
        
        print("   Completed simulation loop. Stopping video recording...")
        
    except Exception as e:
        print(f"Error during simulation execution: {e}")
        
    finally:
        print("Stopping ffmpeg process...")
        ffmpeg_process.send_signal(signal.SIGINT)
        try:
            ffmpeg_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
            
    if os.path.exists(video_path):
        print(f"\n🎉 SUCCESS! Live simulation demonstration video saved at: {video_path}")
        print(f"File size: {os.path.getsize(video_path) / (1024*1024):.2f} MB")
        
        # Copy to artifacts directory
        dest_artifact_path = "/home/arihant/.gemini/antigravity/brain/1930df2c-3f88-4400-afb2-11d998c20c95/artifacts/drony_dynamic_remembr.mp4"
        try:
            subprocess.call(["cp", video_path, dest_artifact_path])
            print(f"   Video copied to artifacts: {dest_artifact_path}")
        except Exception as cp_err:
            print(f"   Warning: Could not copy video to artifacts: {cp_err}")
    else:
        print("\n❌ Error: Failed to generate video file.")

if __name__ == "__main__":
    record_live_flight()
