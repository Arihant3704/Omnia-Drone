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
    print("Finding gazebo window via xwininfo...")
    tree = run_cmd("xwininfo -root -tree")
    
    gazebo_win_id = None
    for line in tree.splitlines():
        if '"gazebo"' in line and ('1558x973' in line or '1556x884' in line):
            m = re.search(r"(0x[0-9a-fA-F]+)", line)
            if m:
                gazebo_win_id = m.group(1)
                break
                
    if not gazebo_win_id:
        print("No gazebo window found in tree!")
        # Fallback to any line containing "gazebo" and a geometry
        for line in tree.splitlines():
            if '"gazebo"' in line:
                m = re.search(r"(0x[0-9a-fA-F]+)", line)
                if m:
                    gazebo_win_id = m.group(1)
                    break
                    
    if not gazebo_win_id:
        print("Could not find any gazebo window.")
        return
        
    print(f"Found Gazebo Window ID: {gazebo_win_id}")
    
    # Activate and raise the window
    print("Activating Gazebo window...")
    run_cmd(f"xdotool windowactivate {gazebo_win_id}")
    time.sleep(1)
    
    # Press Ctrl+t to open Topic Selector
    print("Sending Ctrl+T...")
    run_cmd(f"xdotool key ctrl+t")
    time.sleep(1.5)
    
    # Type 'depth_camera' and press enter
    print("Typing topic 'depth_camera'...")
    run_cmd("xdotool type depth_camera")
    time.sleep(1)
    
    print("Pressing Return...")
    run_cmd("xdotool key Return")
    time.sleep(1)
    
    print("Topic visualization opened!")

if __name__ == "__main__":
    main()
