import subprocess
import os
import re
import cv2
import mss
import numpy as np
import time

def run_test():
    env = {"DISPLAY": ":1"}
    
    # Get window list
    res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
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
        
    small_win_id = None
    for line in lines:
        if '"gazebo"' in line and '160x160' in line:
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                small_win_id = m.group(1)
                break
                
    if not small_win_id:
        print("Small floating window not found!")
        return
        
    print(f"Found small camera window: {small_win_id}")
    
    # Try resizing it using xdotool
    print("Resizing camera window to 640x480...")
    subprocess.run(["xdotool", "windowsize", small_win_id, "640", "480"], env=env)
    time.sleep(1)
    
    # Get new window tree to check size and position
    res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
    lines = res.stdout.splitlines()
    for line in lines:
        if small_win_id in line:
            print(f"Updated window info: {line.strip()}")
            # Find the geometry part
            # e.g., 640x480+0+0  +270+137
            # We want the absolute coordinates at the end: +270+137
            m_geom = re.search(r"(\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)", line)
            if m_geom:
                w = int(m_geom.group(1))
                h = int(m_geom.group(2))
                x = int(m_geom.group(3))
                y = int(m_geom.group(4))
                print(f"Capturing: {w}x{h} at ({x}, {y})")
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x, "width": w, "height": h}
                    img = np.array(sct.grab(monitor))
                    cv2.imwrite("/tmp/test_resized_camera.png", img)
                    print(f"Captured resized camera image to /tmp/test_resized_camera.png with size {img.shape}")
            break

if __name__ == "__main__":
    run_test()
