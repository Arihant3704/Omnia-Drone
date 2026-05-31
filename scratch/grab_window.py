import mss
import numpy as np
import cv2

def main():
    # Geometry of 0x440004f: 640x480 at +270+137
    x = 270
    y = 137
    w = 640
    h = 480
    
    with mss.mss() as sct:
        monitor = {"top": y, "left": x, "width": w, "height": h}
        img = np.array(sct.grab(monitor))
        cv2.imwrite("/tmp/test_grab_0x440004f.png", img)
        print("Saved /tmp/test_grab_0x440004f.png")

if __name__ == "__main__":
    main()
