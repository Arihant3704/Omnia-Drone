import subprocess
import time
import os
import mss
import numpy as np
import cv2

def run_cmd(cmd):
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res.stdout.strip()

def main():
    print("Activating Gazebo...")
    # Find Gazebo window ID
    tree = run_cmd("xwininfo -root -tree")
    gazebo_win_id = None
    for line in tree.splitlines():
        if '"Gazebo"' in line:
            gazebo_win_id = line.split()[0]
            break
            
    if not gazebo_win_id:
        print("No Gazebo window found.")
        return
        
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    run_cmd(f"xdotool windowraise {gazebo_win_id}")
    time.sleep(1)
    
    # We will click the "Window" menu at (188, 78)
    print("Clicking 'Window' menu...")
    run_cmd("xdotool mousemove 188 78 click 1")
    time.sleep(1)
    
    # Take screenshot of the open menu
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/menu_open.png", img)
        print("Menu screenshot saved to /tmp/menu_open.png")

if __name__ == "__main__":
    main()
