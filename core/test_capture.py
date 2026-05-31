import subprocess
import re
import cv2
import mss
import numpy as np

def test_capture():
    env = {"DISPLAY": ":1"}
    res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
    lines = res.stdout.splitlines()
    print("Found windows:")
    for line in lines:
        if '"gazebo"' in line or '"Gazebo"' in line:
            print(line.strip())

if __name__ == "__main__":
    test_capture()
