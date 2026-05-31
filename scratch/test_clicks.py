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
    tree = run_cmd("xwininfo -root -tree")
    gazebo_win_id = None
    for line in tree.splitlines():
        if '"Gazebo"' in line:
            gazebo_win_id = line.split()[0]
            break
            
    if not gazebo_win_id:
        print("No Gazebo window.")
        return
        
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    time.sleep(1)
    
    # We will test X from 100 to 250 in steps of 20
    for x in range(100, 260, 20):
        print(f"Clicking at X={x}, Y=78...")
        # First close any open menus by clicking in the center of the window
        run_cmd("xdotool mousemove 900 500 click 1")
        time.sleep(0.5)
        # Click the menu item
        run_cmd(f"xdotool mousemove {x} 78 click 1")
        time.sleep(1)
        
        # Capture and save
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = np.array(sct.grab(monitor))
            # Crop the menu area to save space
            # Menu area is roughly top-left: 0, 64 to 400, 400
            crop = img[64:450, 0:400]
            cv2.imwrite(f"/tmp/menu_x_{x}.png", crop)

if __name__ == "__main__":
    main()
