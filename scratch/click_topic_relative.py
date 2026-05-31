import subprocess
import time
import os
import mss
import numpy as np
import cv2
import re

def run_cmd(cmd):
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res.stdout.strip()

def main():
    # 1. Close any open dialogs first
    print("Resetting focus...")
    run_cmd("xdotool mousemove 900 500 click 1")
    time.sleep(0.5)
    
    # 2. Open Topic Selector
    print("Opening Topic Selector...")
    run_cmd("xdotool mousemove 220 78 click 1")
    time.sleep(0.5)
    run_cmd("xdotool key Down")
    time.sleep(0.2)
    run_cmd("xdotool key Return")
    time.sleep(2.0)
    
    # 3. Find the Topic Selector window ID
    tree = run_cmd("xwininfo -root -tree")
    dialog_win_id = None
    for line in tree.splitlines():
        if '"gazebo"' in line and "576x320" in line:
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                dialog_win_id = m.group(1)
                break
                
    if not dialog_win_id:
        print("Could not find Topic Selector dialog window!")
        return
        
    print(f"Topic Selector Dialog Window ID: {dialog_win_id}")
    
    # 4. Click the expand arrow of gazebo.msgs.ImageStamped
    # Relative coordinates: X=15, Y=148
    print("Clicking expand arrow...")
    run_cmd(f"xdotool mousemove --window {dialog_win_id} 15 148 click 1")
    time.sleep(1.0)
    
    # 5. Double click the child topic
    # Relative coordinates: X=100, Y=166
    print("Double clicking child topic...")
    run_cmd(f"xdotool mousemove --window {dialog_win_id} 100 166 click 1")
    time.sleep(0.1)
    run_cmd(f"xdotool mousemove --window {dialog_win_id} 100 166 click 1")
    time.sleep(2.0)
    
    # 6. Take screenshot
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/after_topic_click.png", img)
        print("Screenshot saved to /tmp/after_topic_click.png")

if __name__ == "__main__":
    main()
