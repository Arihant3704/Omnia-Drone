import subprocess
import os
import re
import cv2
import mss
import numpy as np
import time

def raise_gazebo():
    try:
        env = {"DISPLAY": ":1"}
        res = subprocess.run(["xdotool", "search", "--name", "^Gazebo$"], capture_output=True, text=True, env=env)
        win_ids = res.stdout.strip().split()
        print(f"Raising Gazebo windows: {win_ids}")
        for win_id in win_ids:
            subprocess.run(["xdotool", "windowactivate", win_id], env=env)
            subprocess.run(["xdotool", "windowraise", win_id], env=env)
    except Exception as e:
        print(f"Error raising Gazebo: {e}")

def run_test():
    raise_gazebo()
    time.sleep(2) # Give window manager time to raise it
    
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
                    
    # Capture the screen for the main viewport and the small floating window
    with mss.mss() as sct:
        # Main viewport (we want the 3D rendering area which is 1556x884 or similar)
        # We look for a child window with width > 600 and height > 400
        main_vp = next(((w, h, x, y) for w, h, x, y, _ in child_wins if w > 600 and h > 400), None)
        if main_vp:
            w, h, x, y = main_vp
            print(f"Capturing main viewport: {w}x{h} at +{x}+{y}")
            monitor = {"top": y, "left": x, "width": w, "height": h}
            img = np.array(sct.grab(monitor))
            cv2.imwrite("/tmp/test_main_viewport.png", img)
            print("Saved /tmp/test_main_viewport.png")
            
        # Small floating window (usually 160x160)
        small_vp = next(((w, h, x, y) for w, h, x, y, _ in child_wins if w == 160 and h == 160), None)
        if small_vp:
            w, h, x, y = small_vp
            print(f"Capturing small viewport: {w}x{h} at +{x}+{y}")
            monitor = {"top": y, "left": x, "width": w, "height": h}
            img = np.array(sct.grab(monitor))
            cv2.imwrite("/tmp/test_small_viewport.png", img)
            print("Saved /tmp/test_small_viewport.png")

if __name__ == "__main__":
    run_test()
