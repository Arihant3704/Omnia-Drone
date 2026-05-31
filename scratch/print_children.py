import subprocess
import re
import os

def run_cmd(cmd):
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res.stdout.strip()

def main():
    tree = run_cmd("xwininfo -root -tree")
    print("ALL WINDOWS CONTAINING GAZEBO/GZ:")
    for line in tree.splitlines():
        if any(w in line.lower() for w in ["gazebo", "gzclient", "gzserver"]):
            print(line.strip())

if __name__ == "__main__":
    main()
