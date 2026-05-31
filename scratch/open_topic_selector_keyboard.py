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
        print("No Gazebo window found.")
        return
        
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    time.sleep(1)
    
    # Click "Window" menu
    print("Clicking 'Window' menu at (220, 78)...")
    run_cmd("xdotool mousemove 220 78 click 1")
    time.sleep(0.5)
    
    # Press Down key
    print("Pressing Down...")
    run_cmd("xdotool key Down")
    time.sleep(0.5)
    
    # Press Return key
    print("Pressing Return...")
    run_cmd("xdotool key Return")
    time.sleep(2)
    
    # Take screenshot of the open dialog
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/keyboard_dialog_open.png", img)
        print("Screenshot saved to /tmp/keyboard_dialog_open.png")

if __name__ == "__main__":
    main()
