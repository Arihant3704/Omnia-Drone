import os
import time
import subprocess
import signal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def record_demo():
    # Make sure DISPLAY is set to :1
    os.environ["DISPLAY"] = ":1"
    
    video_dir = "/home/arihant/simulation/demo_videos"
    video_path = os.path.join(video_dir, "remembr_demo.mp4")
    
    # Clean up old video if it exists
    if os.path.exists(video_path):
        os.remove(video_path)
        
    print("1. Starting ffmpeg screen capture on DISPLAY=:1 in the background...")
    # Capture display :1.0, 1920x1080 resolution, 30fps
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "x11grab",
        "-video_size", "1920x1080",
        "-framerate", "30",
        "-i", ":1.0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        video_path
    ]
    
    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)  # Let ffmpeg initialize
    
    print("2. Starting Selenium Webdriver with headful Chrome...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        url = "http://localhost:8501"
        print(f"3. Navigating to {url}...")
        driver.get(url)
        
        # Wait for page elements to load
        time.sleep(8)
        
        print("4. Locating and clicking on ReMEmbR Vector DB tab...")
        # Streamlit tab headers are buttons/divs inside a tablist
        tab_xpath = "//button[contains(., 'NVIDIA ReMEmbR Vector DB')]"
        wait = WebDriverWait(driver, 10)
        remembr_tab = wait.until(EC.element_to_be_clickable((By.XPATH, tab_xpath)))
        remembr_tab.click()
        time.sleep(4)
        
        print("5. Performing semantic query: 'injured worker'...")
        # Find input inside the active tab
        # Typically the search input has a placeholder or label
        # Let's find inputs in the DOM
        inputs = driver.find_elements(By.TAG_NAME, "input")
        search_input = None
        for inp in inputs:
            placeholder = inp.get_attribute("placeholder") or ""
            if "search" in placeholder.lower() or "query" in placeholder.lower():
                search_input = inp
                break
        
        if not search_input and inputs:
            # Fallback to the first text input found
            for inp in inputs:
                if inp.get_attribute("type") == "text":
                    search_input = inp
                    break
                    
        if search_input:
            search_input.clear()
            search_input.send_keys("injured worker")
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            print("   Submitted search. Waiting for results...")
            time.sleep(6)
            
            print("6. Performing semantic query: 'red toolbox'...")
            # Select all text and clear
            search_input.send_keys(Keys.CONTROL + "a")
            search_input.send_keys(Keys.BACKSPACE)
            time.sleep(1)
            search_input.send_keys("red toolbox")
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            print("   Submitted search. Waiting for results...")
            time.sleep(6)
            
            print("7. Clearing search to show timeline...")
            search_input.send_keys(Keys.CONTROL + "a")
            search_input.send_keys(Keys.BACKSPACE)
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            time.sleep(4)
        else:
            print("   Warning: Could not find search input field!")
            
        print("8. Scrolling page to show memory timeline and SLAM map...")
        # Scroll down slightly
        driver.execute_script("window.scrollTo(0, 400);")
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(3)
        
        print("9. Completed UI actions. Closing browser...")
        
    except Exception as e:
        print(f"Error during browser interaction: {e}")
        
    finally:
        driver.quit()
        print("10. Stopping ffmpeg recording...")
        ffmpeg_process.send_signal(signal.SIGINT)
        # Wait for ffmpeg to gracefully save the video
        try:
            ffmpeg_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
            
    if os.path.exists(video_path):
        print(f"\n🎉 SUCCESS! Demonstration video saved at: {video_path}")
        print(f"File size: {os.path.getsize(video_path) / (1024*1024):.2f} MB")
    else:
        print("\n❌ Error: Failed to generate video file.")

if __name__ == "__main__":
    record_demo()
