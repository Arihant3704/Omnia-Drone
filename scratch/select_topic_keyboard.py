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
    # Make sure we focus the Topic Selector dialog
    # The Topic Selector dialog should already be open and focused.
    # Let's type 'image' to select gazebo.msgs.ImageStamped
    print("Typing 'image'...")
    run_cmd("xdotool type --delay 100 image")
    time.sleep(0.8)
    
    # Expand the node by pressing Right arrow
    print("Pressing Right arrow...")
    run_cmd("xdotool key Right")
    time.sleep(0.5)
    
    # Press Down arrow to highlight the child topic
    print("Pressing Down arrow...")
    run_cmd("xdotool key Down")
    time.sleep(0.5)
    
    # Press Return to accept
    print("Pressing Return...")
    run_cmd("xdotool key Return")
    time.sleep(2)
    
    # Take screenshot of the screen
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/after_topic_selected.png", img)
        print("Screenshot saved to /tmp/after_topic_selected.png")

if __name__ == "__main__":
    main()
