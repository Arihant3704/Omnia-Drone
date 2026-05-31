import subprocess
import time
import os
import re

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
        # Look for the main window (e.g., width > 1000, height > 800, name contains "Gazebo" or "gazebo")
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
    
    # Send Ctrl+T
    print("Sending Ctrl+T...")
    run_cmd(f"xdotool key --window {gazebo_win_id} ctrl+t")
    time.sleep(2)
    
    # Let's type 'depth_camera' and press return
    print("Typing topic name 'depth_camera'...")
    run_cmd("xdotool type --delay 100 depth_camera")
    time.sleep(1)
    
    print("Pressing Return...")
    run_cmd("xdotool key Return")
    time.sleep(2)
    
    print("Checking window tree for new camera visualization window...")
    new_tree = run_cmd("xwininfo -root -tree")
    for line in new_tree.splitlines():
        if "gazebo" in line.lower() and ("camera" in line.lower() or "image" in line.lower() or "depth" in line.lower()):
            print(f"Found match: {line.strip()}")

if __name__ == "__main__":
    main()
