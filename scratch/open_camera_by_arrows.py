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
    
    # First click inside the center of Gazebo to close any open dropdowns or dialogs
    print("Resetting focus...")
    run_cmd("xdotool mousemove 900 500 click 1")
    time.sleep(0.5)
    
    # Click "Window" menu
    print("Clicking 'Window' menu...")
    run_cmd("xdotool mousemove 220 78 click 1")
    time.sleep(0.5)
    
    # Press Down and Return to open Topic Selector
    print("Opening Topic Selector...")
    run_cmd("xdotool key Down")
    time.sleep(0.2)
    run_cmd("xdotool key Return")
    time.sleep(2.0)
    
    # Press Down 6 times to highlight gazebo.msgs.ImageStamped
    print("Navigating to ImageStamped...")
    for _ in range(6):
        run_cmd("xdotool key Down")
        time.sleep(0.1)
        
    # Press Right to expand
    print("Expanding node...")
    run_cmd("xdotool key Right")
    time.sleep(0.5)
    
    # Press Down once to select the child
    print("Selecting child topic...")
    run_cmd("xdotool key Down")
    time.sleep(0.3)
    
    # Press Return to accept
    print("Confirming selection...")
    run_cmd("xdotool key Return")
    time.sleep(2.0)
    
    # Take screenshot of the screen
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/camera_open_attempt.png", img)
        print("Screenshot saved to /tmp/camera_open_attempt.png")

if __name__ == "__main__":
    main()
