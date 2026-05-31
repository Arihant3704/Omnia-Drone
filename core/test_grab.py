import mss
import numpy as np
import cv2

def main():
    with mss.mss() as sct:
        # 160x160 window at +270+137 on DISPLAY=:1
        monitor = {"top": 137, "left": 270, "width": 160, "height": 160}
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/omnia_cam_test.png", img)
        print("Screenshot saved to /tmp/omnia_cam_test.png")

if __name__ == "__main__":
    main()
