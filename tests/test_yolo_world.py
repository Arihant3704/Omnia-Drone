from ultralytics import YOLOWorld
import torch
import numpy as np
import cv2
import time

def test_yolo_world():
    print(f"CUDA Available: {torch.cuda.is_available()}")
    device = '0' if torch.cuda.is_available() else 'cpu'
    
    print("Loading YOLO-World model (this may download weights)...")
    # Using small model for speed
    model = YOLOWorld('yolov8s-world.pt')
    
    # 1. Demonstrate Open-Vocabulary: Set custom classes
    custom_classes = ["red backpack", "person with a hat", "blue car"]
    print(f"Setting custom open-vocabulary classes: {custom_classes}")
    model.set_classes(custom_classes)
    
    # 2. Run a dummy inference to test GPU warm-up
    dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
    print("Running initial inference on GPU...")
    start_time = time.time()
    results = model.predict(dummy_img, device=device, verbose=False)
    end_time = time.time()
    
    print(f"Inference successful! Time taken: {end_time - start_time:.4f}s")
    print("YOLO-World is ready for the Agentic Pilot.")

if __name__ == "__main__":
    test_yolo_world()
