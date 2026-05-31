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
    print("Finding window IDs...")
    tree = run_cmd("xwininfo -root -tree")
    
    gazebo_win_id = None
    vscode_win_id = None
    for line in tree.splitlines():
        # Match the main Gazebo window: must contain "Gazebo" (exact case) or have height > 900 and contain "gazebo"
        if '"Gazebo"' in line:
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                gazebo_win_id = m.group(1)
        elif '"gazebo"' in line and gazebo_win_id is None:
            # Fallback check for height > 900
            m_geom = re.search(r"(\d+)x(\d+)[+-]", line)
            if m_geom:
                h = int(m_geom.group(2))
                if h > 900:
                    m = re.search(r"(0x[0-9a-fA-F]+)", line)
                    if m:
                        gazebo_win_id = m.group(1)
                        
        if "antigravity" in line.lower() and "1846x" in line:
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                vscode_win_id = m.group(1)
                
    print(f"Main Gazebo Window ID: {gazebo_win_id}, VSCode Window ID: {vscode_win_id}")
    
    if not gazebo_win_id:
        print("Could not find main Gazebo window!")
        return

    if vscode_win_id:
        print("Minimizing VSCode window...")
        run_cmd(f"xdotool windowminimize {vscode_win_id}")
        time.sleep(1)
        
    print("Activating Gazebo window...")
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    run_cmd(f"xdotool windowraise {gazebo_win_id}")
    time.sleep(1)
    
    # Let's send a click to the center of the Gazebo window first to focus it
    geom_res = run_cmd(f"xwininfo -id {gazebo_win_id}")
    print(f"Gazebo geometry details:\n{geom_res}")
    
    # Parse width, height, absolute X, Y from geometry details
    w_match = re.search(r"Width:\s+(\d+)", geom_res)
    h_match = re.search(r"Height:\s+(\d+)", geom_res)
    x_match = re.search(r"Absolute upper-left X:\s+(\d+)", geom_res)
    y_match = re.search(r"Absolute upper-left Y:\s+(\d+)", geom_res)
    
    if w_match and h_match and x_match and y_match:
        w = int(w_match.group(1))
        h = int(h_match.group(1))
        x = int(x_match.group(1))
        y = int(y_match.group(1))
        
        click_x = x + w // 2
        click_y = y + h // 2
        print(f"Clicking center of Gazebo window at ({click_x}, {click_y}) to ensure focus...")
        run_cmd(f"xdotool mousemove {click_x} {click_y} click 1")
        time.sleep(1)

    # Send Ctrl+T
    print("Sending Ctrl+T...")
    run_cmd(f"xdotool key ctrl+t")
    time.sleep(2)
    
    # Type 'depth_camera'
    print("Typing topic...")
    run_cmd("xdotool type --delay 100 depth_camera")
    time.sleep(1)
    
    # Press Return
    print("Pressing Return...")
    run_cmd("xdotool key Return")
    time.sleep(2)
        
    # Capture screen
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/screen_after_t.png", img)
        print("Screen captured to /tmp/screen_after_t.png")

if __name__ == "__main__":
    main()
