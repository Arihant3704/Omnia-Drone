import subprocess
import time
import os
import re
import cv2
import mss
import numpy as np

def run_test():
    # Start PX4 SITL + Gazebo with iris_depth_camera
    env = {"DISPLAY": ":1", "PX4_SITL_WORLD": "sar_demo"}
    print("Starting simulation...")
    proc = subprocess.Popen(
        ["make", "px4_sitl", "gazebo-classic_iris_depth_camera"],
        cwd="/home/arihant/simulation/PX4-Autopilot",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for simulation to startup
    time.sleep(20)
    
    # Get window list
    res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env={"DISPLAY": ":1"})
    lines = res.stdout.splitlines()
    
    # Find Gazebo window and its children
    gazebo_win_id = None
    for line in lines:
        if '"Gazebo"' in line:
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                gazebo_win_id = m.group(1)
                break
    
    if not gazebo_win_id:
        print("Gazebo window not found!")
        proc.terminate()
        return
        
    print(f"Found Gazebo window: {gazebo_win_id}")
    
    # List all child windows of Gazebo
    child_wins = []
    gazebo_index = -1
    for idx, line in enumerate(lines):
        if gazebo_win_id in line:
            gazebo_index = idx
            break
            
    if gazebo_index != -1:
        for line in lines[gazebo_index+1:]:
            if '"gazebo"' in line:
                match = re.search(r"(\d+)x(\d+)\+\d+\+\d+\s+\+(\d+)\+(\d+)", line)
                if match:
                    w, h, x, y = map(int, match.groups())
                    child_wins.append((w, h, x, y, line.strip()))
                    
    print("Child windows of Gazebo:")
    for w, h, x, y, desc in child_wins:
        print(f"  Size: {w}x{h}, Pos: +{x}+{y} | {desc}")
        
    # Capture the screen for the main viewport and the small floating window
    with mss.mss() as sct:
        # Main viewport (usually width > 600)
        main_vp = next(((w, h, x, y) for w, h, x, y, _ in child_wins if w > 600), None)
        if main_vp:
            w, h, x, y = main_vp
            print(f"Capturing main viewport: {w}x{h} at +{x}+{y}")
            monitor = {"top": y, "left": x, "width": w, "height": h}
            img = np.array(sct.grab(monitor))
            cv2.imwrite("/tmp/test_main_viewport.png", img)
            
        # Small floating window (usually 160x160)
        small_vp = next(((w, h, x, y) for w, h, x, y, _ in child_wins if w == 160 and h == 160), None)
        if small_vp:
            w, h, x, y = small_vp
            print(f"Capturing small viewport: {w}x{h} at +{x}+{y}")
            monitor = {"top": y, "left": x, "width": w, "height": h}
            img = np.array(sct.grab(monitor))
            cv2.imwrite("/tmp/test_small_viewport.png", img)
            
    # Terminate the simulation
    print("Terminating simulation...")
    proc.terminate()
    time.sleep(2)
    subprocess.run(["kill", "-9", str(proc.pid)], stderr=subprocess.DEVNULL)
    subprocess.run(["killall", "-9", "px4", "gzserver", "gzclient"], stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    run_test()
