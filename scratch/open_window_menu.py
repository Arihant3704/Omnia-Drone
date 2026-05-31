import subprocess
import time
import os
import re
import mss
import numpy as np
import cv2

def run_cmd(cmd):
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res.stdout.strip()

def main():
    print("Finding main Gazebo window...")
    tree = run_cmd("xwininfo -root -tree")
    
    gazebo_win_id = None
    for line in tree.splitlines():
        if ("gazebo" in line.lower()) and ("1846x" in line or "1558x" in line or "1556x" in line or "1920x" in line):
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                gazebo_win_id = m.group(1)
                break
                
    if not gazebo_win_id:
        print("Could not find main Gazebo window.")
        return
        
    print(f"Main Gazebo Window ID: {gazebo_win_id}")
    
    # Focus the main window
    print("Activating main window...")
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    time.sleep(1)
    
    # Send Alt+w
    print("Sending Alt+w...")
    run_cmd(f"xdotool key --window {gazebo_win_id} alt+w")
    time.sleep(1.5)
    
    # Capture screen
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/screen_menu.png", img)
        print("Menu screen captured to /tmp/screen_menu.png")

if __name__ == "__main__":
    main()
