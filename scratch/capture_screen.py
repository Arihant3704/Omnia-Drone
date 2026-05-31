import mss
import numpy as np
import cv2

def main():
    with mss.mss() as sct:
        # Capture the entire primary monitor
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/screen.png", img)
        print("Whole screen captured to /tmp/screen.png")

if __name__ == "__main__":
    main()
