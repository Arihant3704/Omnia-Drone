import threading
from dronekit import connect, VehicleMode, LocationGlobalRelative # type: ignore
import time
import math
from pymavlink import mavutil # type: ignore
import os
import json
import numpy as np
import mss # type: ignore
import datetime
import cv2
import subprocess
import re

def get_gazebo_viewport():
    default_vp = (1779, 238, 1081, 875)
    try:
        env = {"DISPLAY": ":1"}
        res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
        lines = res.stdout.splitlines()
        gazebo_win_id = None
        for line in lines:
            if '"Gazebo"' in line:
                m = re.search(r"(0x[0-9a-fA-F]+)", line)
                if m:
                    gazebo_win_id = m.group(1)
                    break
        if not gazebo_win_id:
            return default_vp
            
        gazebo_index = -1
        for idx, line in enumerate(lines):
            if gazebo_win_id in line:
                gazebo_index = idx
                break
                
        if gazebo_index == -1:
            return default_vp

        # 1. Search for FPV camera floating window (160x160 or already resized to 640x480)
        camera_win_id = None
        camera_win_geom = None
        for line in lines[gazebo_index+1:]:
            if '"gazebo"' in line:
                m = re.search(r"(0x[0-9a-fA-F]+)", line)
                m_geom = re.search(r"(\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)", line)
                if m and m_geom:
                    win_id = m.group(1)
                    w = int(m_geom.group(1))
                    h = int(m_geom.group(2))
                    x = int(m_geom.group(3))
                    y = int(m_geom.group(4))
                    if (w == 160 and h == 160) or (w == 640 and h == 480):
                        camera_win_id = win_id
                        camera_win_geom = (x, y, w, h)
                        break

        if camera_win_id:
            if camera_win_geom[2] == 160:
                # Resize it to 640x480
                subprocess.run(["xdotool", "windowsize", camera_win_id, "640", "480"], env=env)
                camera_win_geom = (camera_win_geom[0], camera_win_geom[1], 640, 480)
            print(f"Dynamically detected and configured Gazebo camera viewport: {camera_win_geom}")
            return camera_win_geom

        # 2. Fallback to main 3D viewport (child window with w > 600 and h > 400)
        fallback_win = None
        for line in lines[gazebo_index+1:]:
            if '"gazebo"' in line:
                m_geom = re.search(r"(\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)", line)
                if m_geom:
                    w = int(m_geom.group(1))
                    h = int(m_geom.group(2))
                    x = int(m_geom.group(3))
                    y = int(m_geom.group(4))
                    if w > 600 and h > 400:
                        fallback_win = (x, y, w, h)
        if fallback_win:
            print(f"Dynamically detected Gazebo main viewport fallback: {fallback_win}")
            return fallback_win
            
    except Exception as e:
        print(f"Error dynamically detecting Gazebo viewport: {e}")
    return default_vp

def raise_gazebo():
    try:
        env = {"DISPLAY": ":1"}
        res = subprocess.run(["xdotool", "search", "--name", "^Gazebo$"], capture_output=True, text=True, env=env)
        win_ids = res.stdout.strip().split()
        for win_id in win_ids:
            subprocess.run(["xdotool", "windowactivate", win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["xdotool", "windowraise", win_id], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error raising Gazebo window: {e}")

# --- DroneKit PX4 Mode Compatibility Monkeypatch ---
# Bypasses the heartbeat listener crash and maps OFFBOARD mode correctly.
original_interpret_px4_mode = mavutil.interpret_px4_mode
def patched_interpret_px4_mode(base_mode, custom_mode):
    custom_main_mode = (custom_mode & 0xFF0000) >> 16
    if custom_main_mode == 6:  # PX4_CUSTOM_MAIN_MODE_OFFBOARD
        return "OFFBOARD"
    return original_interpret_px4_mode(base_mode, custom_mode)
mavutil.interpret_px4_mode = patched_interpret_px4_mode

# --- Drone Connection Logic ---
def get_vehicle():
    connection_ports = ['udp:127.0.0.1:14540', 'udp:127.0.0.1:14550', 'udp:127.0.0.1:14580']
    for conn in connection_ports:
        try:
            print(f'Attempting to connect on {conn}...')
            v = connect(conn, wait_ready=True, heartbeat_timeout=15)
            print(f'>>> SUCCESS: Drone connected on {conn}')
            return v
        except Exception as e:
            print(f'Failed on {conn}: {e}')
    return None

vehicle = get_vehicle()

if not vehicle:
    print("CRITICAL: Could not connect to drone on any standard port. Check PX4 log.")
    exit(1)

# Lidar sensor values dictionary
drone_id = os.environ.get("DRONE_ID", "drone_1")

lidar_distances = {
    "forward": 999.0,
    "right": 999.0,
    "backward": 999.0,
    "left": 999.0,
    "downward": 999.0
}

def distance_sensor_listener(self, name, message):
    global lidar_distances
    # current_distance is in cm
    dist_m = message.current_distance / 100.0
    orient = message.orientation
    # orientations:
    # 0 = MAV_SENSOR_ROTATION_NONE (forward)
    # 2 = MAV_SENSOR_ROTATION_YAW_90 (right)
    # 6 = MAV_SENSOR_ROTATION_YAW_270 (left)
    # 25 = MAV_SENSOR_ROTATION_PITCH_270 (downward)
    if orient == 0:
        lidar_distances["forward"] = dist_m
    elif orient == 2:
        lidar_distances["right"] = dist_m
    elif orient == 6:
        lidar_distances["left"] = dist_m
    elif orient == 25:
        lidar_distances["downward"] = dist_m

vehicle.add_message_listener('DISTANCE_SENSOR', distance_sensor_listener)

# Define the stop_requested variable
stop_requested = False
is_executing_command = False
target_mode = None
abort_fifo_path = '/tmp/gpt_abort_fifo'
command_fifo_path = '/tmp/gpt_command_fifo'
comin_fifo_path = '/tmp/gpt_comin_fifo'
status_fifo_path = '/tmp/gpt_status_fifo'
statusa_fifo_path = '/tmp/gpt_statusa_fifo'
img_fifo_path = '/tmp/gpt_img_fifo'
imgcont_fifo_path = '/tmp/gpt_imgcont_fifo'
seecont_fifo_path = '/tmp/gpt_seecont_fifo'
imgcontnew_fifo_path = '/tmp/gpt_imgcontnew_fifo'

# Your specified folder for storing screenshots
screenshot_folder = "./captures"

def take_screenshot():
    """Capture a screenshot of the specified region and save it to the specified folder."""
    # Ensure the folder exists
    if not os.path.exists(screenshot_folder):
        os.makedirs(screenshot_folder)
    
    raise_gazebo()
    viewport = get_gazebo_viewport()
    
    with mss.mss() as sct:
        monitor = {"top": viewport[1], "left": viewport[0], "width": viewport[2], "height": viewport[3]}
        sct_img = sct.grab(monitor)
        img = np.array(sct_img)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    
    # Create a timestamped filename for the screenshot
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    
    # Create the full file path
    file_path = os.path.join(screenshot_folder, filename)
    
    # Save the screenshot
    cv2.imwrite(file_path, img)
    print(f"Screenshot saved to: {file_path}")

# Ensure the status FIFO exists
if not os.path.exists(statusa_fifo_path):
    os.mkfifo(statusa_fifo_path)

for fifo_path in [command_fifo_path, abort_fifo_path]:
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path)

def arm_and_takeoff(aTargetAltitude):
    """
    Arms vehicle and flies to aTargetAltitude (PX4 style).
    """
    print("Basic pre-arm checks")
    arm_check_count = 0
    while not vehicle.is_armable and arm_check_count < 5:
        if stop_requested:
            return 'stop'
        print(f"Waiting for vehicle to initialise... (is_armable: {vehicle.is_armable})")
        time.sleep(1)
        arm_check_count += 1

    print("Arming motors")
    vehicle.mode = VehicleMode("TAKEOFF")
    time.sleep(1)
    vehicle.armed = True

    arm_wait_count = 0
    while not vehicle.armed and arm_wait_count < 10:
        if stop_requested:
            return 'stop'
        print("Waiting for arming...")
        vehicle.armed = True
        time.sleep(1)
        arm_wait_count += 1

    print("Taking off!")
    while True:
        if stop_requested:
            return 'stop'
        current_altitude = vehicle.location.global_relative_frame.alt
        print(f"Altitude: {current_altitude}")
        if current_altitude >= aTargetAltitude * 0.95:
            print("Reached target altitude")
            break
        time.sleep(1)
        
    print(">>> Transitioning directly to OFFBOARD mode...")
    init_msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0, 0, 0,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000111111000111,
        0, 0, 0,
        0, 0, 0,
        0, 0, 0, 0, 0
    )
    for _ in range(10):
        vehicle.send_mavlink(init_msg)
        time.sleep(0.1)
    global target_mode
    target_mode = "OFFBOARD"
    vehicle.mode = VehicleMode("OFFBOARD")
    for _ in range(10):
        vehicle.send_mavlink(init_msg)
        time.sleep(0.1)
    target_mode = None
    return True


def set_yaw(angle, direction, relative=False):
    """
    Sets the vehicle's yaw to a specific heading using OFFBOARD setpoints.
    """
    import math
    current_heading = vehicle.heading
    if relative:
        target_heading = (current_heading + (angle if direction == 'C' else -angle)) % 360
    else:
        target_heading = angle % 360

    # Convert target heading (0..360) to rad (-pi..pi) for MAVLink
    target_yaw_rad = math.radians(target_heading)
    if target_yaw_rad > math.pi:
        target_yaw_rad -= 2 * math.pi

    # Send local NED setpoint (velocity 0, target yaw angle)
    msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0,       # time_boot_ms (not used)
        0, 0,    # target system, target component
        mavutil.mavlink.MAV_FRAME_LOCAL_NED, # frame
        0b0000101111000111, # type_mask (velocity enabled, yaw enabled)
        0, 0, 0, # x, y, z positions (ignored)
        0, 0, 0, # x, y, z velocity (set to 0 to hold position)
        0, 0, 0, # x, y, z acceleration (ignored)
        target_yaw_rad, 0) # yaw (rad), yaw_rate (ignored)

    # Wait for the yaw to complete, sending setpoints continuously at 10Hz
    start_time = time.time()
    while True:
        if stop_requested:
            return 'stop'
        vehicle.send_mavlink(msg)
        
        current = vehicle.heading
        # Calculate shortest angular distance
        diff = abs(current - target_heading)
        if diff > 180:
            diff = 360 - diff
        if diff < 2:  # Threshold for heading accuracy
            print(f">>> Yaw completed. Heading: {current:.1f} deg")
            break
        if time.time() - start_time > 8:  # Timeout for yaw action
            print(f"Yaw command timed out. Current heading: {current:.1f} deg, target: {target_heading:.1f} deg")
            break
        time.sleep(0.1)
    return True

def send_ned_velocity(velocity_x, velocity_y, velocity_z, duration):
    """
    Move vehicle in direction based on specified velocity vectors.
    """
    msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0,       # time_boot_ms (not used)
        0, 0,    # target system, target component
        mavutil.mavlink.MAV_FRAME_LOCAL_NED, # frame
        0b0000111111000111, # type_mask (only speeds enabled)
        0, 0, 0, # x, y, z positions (not used)
        velocity_x, velocity_y, velocity_z, # x, y, z velocity in m/s
        0, 0, 0, # x, y, z acceleration (not used)
        0, 0)    # yaw, yaw_rate (not used)

    # send command to vehicle on 10 Hz cycle to prevent OFFBOARD timeout
    steps = int(duration * 10)
    for x in range(steps):
        if stop_requested:
            print(">>> Velocity Move Aborted by user request.")
            break
            
        # Collision avoidance check (safety threshold: 1.5 meters)
        dangerous_obstacles = []
        for name in ["forward", "right", "left"]:
            dist = lidar_distances[name]
            if 0.25 < dist < 1.5:
                dangerous_obstacles.append((name, dist))
                
        if dangerous_obstacles:
            obs_details = ", ".join([f"{name}={dist:.2f}m" for name, dist in dangerous_obstacles])
            print(f">>> [SAFETY] COLLISION AVOIDANCE TRIGGERED! Obstacles: {obs_details}")
            # Send zero velocity commands to brake
            stop_msg = vehicle.message_factory.set_position_target_local_ned_encode(
                0, 0, 0,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111000111,
                0, 0, 0,
                0, 0, 0,
                0, 0, 0, 0, 0
            )
            for _ in range(5):
                vehicle.send_mavlink(stop_msg)
                time.sleep(0.05)
            break

        vehicle.send_mavlink(msg)
        
        # Also update status while moving (every 1 second / 10 steps)
        if x % 10 == 0:
            try:
                status = f"ALT: {vehicle.location.global_relative_frame.alt:.1f}m | MODE: {vehicle.mode.name}"
                fifowrite('/tmp/gpt_status_fifo', status + '\n')
            except: pass
            
        time.sleep(0.1)


def calculate_target_coordinates(distance, bearing):
    R = 6378137.0  # Earth radius in meters
    distance_in_radians = distance / R

    current_lat = vehicle.location.global_relative_frame.lat
    current_lon = vehicle.location.global_relative_frame.lon

    lat1 = math.radians(current_lat)
    lon1 = math.radians(current_lon)
    bearing = math.radians(bearing)

    lat2 = math.asin(math.sin(lat1) * math.cos(distance_in_radians) +
                     math.cos(lat1) * math.sin(distance_in_radians) * math.cos(bearing))

    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(distance_in_radians) * math.cos(lat1),
                             math.cos(distance_in_radians) - math.sin(lat1) * math.sin(lat2))

    new_lat = math.degrees(lat2)
    new_lon = math.degrees(lon2)

    return new_lat, new_lon

def fiforead(fifo_path):
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path)
    try:
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'r') as fifo:
            return fifo.read()
    except Exception as e:
        return ""

def fifowrite(fifo_path, whatToWrite):
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path)
    try:
        fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'w') as fifo:
            fifo.write(whatToWrite)
    except Exception as e:
        pass


def move_to_target(target_lat, target_lon, target_alt=None):
    if target_alt is not None:
        target_location = LocationGlobalRelative(target_lat, target_lon, target_alt)
    else:
        target_location = LocationGlobalRelative(target_lat, target_lon, vehicle.location.global_relative_frame.alt)
    vehicle.simple_goto(target_location)

    while not stop_requested:
        current_location = vehicle.location.global_relative_frame
        dist_to_target = get_distance_metres(current_location, target_location)
        
        if target_alt is not None:
            alt_diff = abs(vehicle.location.global_relative_frame.alt - target_alt)
        else:
            alt_diff = 0
        
        if dist_to_target <= 1.5 and alt_diff <= 0.8:
            print("Reached target location")
            break
        time.sleep(1)
    
    if stop_requested:
        stop_drone()
        return 'stop'

def get_distance_metres(aLocation1, aLocation2):
    dlat = aLocation2.lat - aLocation1.lat
    dlong = aLocation2.lon - aLocation1.lon
    return math.sqrt((dlat * dlat) + (dlong * dlong)) * 1.113195e5

def set_altitude(altitude):
    result = move_to_target(vehicle.location.global_relative_frame.lat,
                            vehicle.location.global_relative_frame.lon,
                            altitude)
    return result

def update_status():
    global stop_requested
    mock_lat = 47.3977506
    mock_lon = 8.545607
    mock_alt = 0.0
    mock_heading = 90.0
    
    while True:
        if stop_requested:
            return
        
        try:
            current_location = vehicle.location.global_relative_frame
            current_heading = vehicle.heading
            lat = current_location.lat
            lon = current_location.lon
            alt = current_location.alt
            bearing = current_heading
        except Exception:
            lat = mock_lat
            lon = mock_lon
            alt = mock_alt
            bearing = mock_heading
            
        status = {
            "drone_id": drone_id,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "bearing": bearing,
            "lidar": lidar_distances
        }
        status_str = json.dumps(status)
        
        # Use non-blocking writes for both status FIFOs to avoid hangs
        fifowrite(status_fifo_path, status_str + '\n')
        fifowrite(statusa_fifo_path, status_str + '\n')
        time.sleep(0.2) 



      
def send_ned_velocity_old(velocity_x, velocity_y, velocity_z, duration):

    msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0, 0, 0,
        mavutil.mavlink.MAV_FRAME_BODY_NED,  # Use the body frame
        0b0000111111000111,  # Bitmask to indicate velocity components are enabled
        0, 0, 0,
        velocity_x, velocity_y, velocity_z,
        0, 0, 0, 0, 0)
    
    # Convert duration to seconds and ensure it runs the full duration even if fractional
    end_time = time.time() + duration
    while time.time() < end_time:
        vehicle.send_mavlink(msg)
        time.sleep(0.1)  # Send the message every 0.1 seconds


def move_circle_with_velocity(radius, portion, steps, velocity, quadrant, clockwise):
    """
    Move the drone in a circular path according to the given parameters using NED velocity.
    """
    angle_increment = (2 * math.pi * portion) / steps
    direction = 1 if clockwise else -1
    
    # Determine the starting angle based on quadrant and direction
    if quadrant == 4:
        start_angle = 0 if clockwise else math.pi / 2
    elif quadrant == 3:
        start_angle = math.pi / 2 if clockwise else math.pi
    elif quadrant == 2:
        start_angle = math.pi if clockwise else 3 * math.pi / 2
    elif quadrant == 1:
        start_angle = 3 * math.pi / 2 if clockwise else 0
    
    # Traverse the circle
    for step in range(steps):
        angle = start_angle + step * angle_increment * direction
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        
        # Calculate the velocities in the body frame
        vx = -velocity * math.sin(angle)
        vy = velocity * math.cos(angle)
        
        # Send the velocity command
        send_ned_velocity_old(vx, vy, 0, angle_increment / velocity)  # Adjust duration based on velocity and angle increment


      
def execute_command(command):
    global stop_requested, target_mode

    if command == 'STOP':
        stop_drone()
        return 'stop'

    try:
        if command.startswith('W'):
            secs = float(command[1:])
            print(f"Waiting for {secs} seconds.")
            for _ in range(int(secs * 10)):  # Check for STOP every 0.1 second
                if stop_requested:
                    return 'stop'
                time.sleep(0.1)
            return True

        if command.startswith('T'):
            target_altitude = float(command[1:])
            return arm_and_takeoff(target_altitude)

        elif command.startswith('ALT'):
            altitude = float(command[3:])
            return set_altitude(altitude)

        elif command.startswith('GOTO'):
            coords = command[5:-1].split(',')
            target_lat = float(coords[0])
            target_lon = float(coords[1])
            return move_to_target(target_lat, target_lon)
        
        elif command.startswith('SEE'):
            # Handle the SEE command by extracting the full context
            see_context_start = command.find('(') + 1
            see_context_end = command.rfind(')')  # Use rfind to find the last closing parenthesis
            see_context = command[see_context_start:see_context_end].strip()

            take_screenshot()
            fifowrite(imgcont_fifo_path, "i")
            fifowrite(imgcontnew_fifo_path, "i")
            time.sleep(0.1)
            fifowrite(seecont_fifo_path, see_context)
            print(f"SEE command processed with context: {see_context}")
            time.sleep(1)
            return True
        
        
                    
            
            
        
        elif command.startswith('CIRC'):
            # Extract the parameters from the CIRC command
            params = command[5:-1].split(',')
            radius = int(params[0])
            portion = float(params[1])
            quadrant = int(params[2])
            clockwise = params[3].strip().lower() == 'true'
            
            return move_circle_with_velocity(radius, portion, 10, 1, quadrant, clockwise)

        elif command[0] in ['A', 'C']:
            direction = command[0]
            angle = float(command[1:])
            return set_yaw(angle, direction, relative=True)

        elif command == 'LAND':
            target_mode = "LAND"
            vehicle.mode = VehicleMode("LAND")
            start_time = time.time()
            while vehicle.mode.name != "LAND" and time.time() - start_time < 5:
                time.sleep(0.1)
            target_mode = None
            return True

        elif command == 'RTL':
            target_mode = "RTL"
            vehicle.mode = VehicleMode("RTL")
            start_time = time.time()
            while vehicle.mode.name != "RTL" and time.time() - start_time < 5:
                time.sleep(0.1)
            target_mode = None
            return True

        elif command[0] in ['F', 'B', 'L', 'R']:
            # --- Smart Auto-Takeoff Logic ---
            if vehicle.location.global_relative_frame.alt < 1.0:
                print(">>> EXECUTING NATIVE PX4 TAKEOFF...")
                
                # Set the flight mode to TAKEOFF before arming
                # This is the secret for PX4: Mode first, then Arm!
                vehicle.mode = VehicleMode("TAKEOFF")
                time.sleep(1)
                
                vehicle.armed = True
                while not vehicle.armed:
                    print(" Waiting for arming...")
                    time.sleep(1)
                
                # Wait for airborne status
                timeout = time.time() + 10
                while time.time() < timeout:
                    if vehicle.location.global_relative_frame.alt > 2.0:
                        print(">>> Drone is AIRBORNE!")
                        break
                    time.sleep(1)
                

            distance = float(command[1:])
            print(f">>> Executing Velocity Move: {command[0]} for {distance}m")
            
            # Reset to OFFBOARD for velocity support if needed
            if vehicle.mode.name != "OFFBOARD":
                print(">>> Switching to OFFBOARD mode...")
                target_mode = "OFFBOARD"
                # Stream a few 0-velocity targets to initialize OFFBOARD mode
                init_msg = vehicle.message_factory.set_position_target_local_ned_encode(
                    0, 0, 0,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                    0b0000111111000111,
                    0, 0, 0,
                    0, 0, 0,
                    0, 0, 0, 0, 0
                )
                for _ in range(10):
                    vehicle.send_mavlink(init_msg)
                    time.sleep(0.1)
                vehicle.mode = VehicleMode("OFFBOARD")
                for _ in range(10):
                    vehicle.send_mavlink(init_msg)
                    time.sleep(0.1)
                target_mode = None

            if command[0] == 'F':
                send_ned_velocity(distance/2, 0, 0, 2) # Move for 2 seconds
            elif command[0] == 'B':
                send_ned_velocity(-distance/2, 0, 0, 2)
            elif command[0] == 'L':
                send_ned_velocity(0, -distance/2, 0, 2)
            elif command[0] == 'R':
                send_ned_velocity(0, distance/2, 0, 2)
                
            print(">>> Movement Chunk Complete.")
            return True

        else:
            print("Invalid command.")
            return False

    except ValueError:
        print("Invalid command format. Please use the correct format.")
        return False

    #return True  # Signal to continue processing further commands

def stop_drone():
    """
    Stops the drone using zero velocity in OFFBOARD mode.
    """
    print("Stopping drone by setting zero velocity in OFFBOARD mode.")
    set_velocity_body(vehicle, 0, 0, 0)
    global stop_requested
    stop_requested = True


def set_velocity_body(vehicle, vx, vy, vz):
    msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0,
        0, 0,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,
        0, 0, 0,
        vx, vy, vz,
        0, 0, 0,
        0, 0)
    vehicle.send_mavlink(msg)

def monitor_abort_fifo():
    global stop_requested
    if not os.path.exists(abort_fifo_path):
        os.mkfifo(abort_fifo_path)
    while True:
        with open(abort_fifo_path, 'r') as fifo:
            command = fifo.read().strip()
            if command.lower() == 'stop':
                stop_requested = True
                stop_drone()

def offboard_heartbeat():
    global is_executing_command, target_mode
    init_msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0, 0, 0,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000111111000111,
        0, 0, 0,
        0, 0, 0,
        0, 0, 0, 0, 0
    )
    while True:
        try:
            current_mode = vehicle.mode.name
            if target_mode is not None and target_mode != "OFFBOARD":
                pass
            elif not is_executing_command:
                vehicle.send_mavlink(init_msg)
        except Exception as e:
            pass
        time.sleep(0.1)

# Set of occupied cells to avoid duplicates and keep it fast
occupied_cells = set()
trajectory_points = []
origin_lat = None
origin_lon = None

def run_slam_mapper():
    global origin_lat, origin_lon, occupied_cells, trajectory_points
    import fcntl
    
    map_file = "/tmp/omnia_map.json"
    
    while True:
        try:
            if not vehicle:
                time.sleep(0.2)
                continue
                
            loc = vehicle.location.global_relative_frame
            if not loc or loc.lat is None or loc.lat == 0.0:
                time.sleep(0.2)
                continue
                
            if origin_lat is None:
                origin_lat = loc.lat
                origin_lon = loc.lon
                print(f"[SLAM] Initialized Origin: Lat={origin_lat}, Lon={origin_lon}")
                
            dx = (loc.lat - origin_lat) * 111319.5
            dy = (loc.lon - origin_lon) * 111319.5 * math.cos(math.radians(origin_lat))
            dz = loc.alt
            bearing = vehicle.heading
            
            # Read existing map data and load obstacles / other drones
            drones_data = {}
            obstacles_data = set()
            origin_data = {"lat": origin_lat, "lon": origin_lon}
            
            if os.path.exists(map_file):
                try:
                    with open(map_file, 'r') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                        data = json.load(f)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
                        obstacles_list = data.get("obstacles", [])
                        for obs in obstacles_list:
                            obstacles_data.add((obs[0], obs[1]))
                            occupied_cells.add((obs[0], obs[1])) # Sync local occupied cells
                            
                        drones_data = data.get("drones", {})
                        if "origin" in data:
                            origin_data = data["origin"]
                except Exception:
                    pass
            
            # Update local trajectory points
            if not trajectory_points or math.sqrt((dx - trajectory_points[-1][0])**2 + (dy - trajectory_points[-1][1])**2) > 0.25:
                trajectory_points.append([round(dx, 2), round(dy, 2)])
                if len(trajectory_points) > 2000:
                    trajectory_points.pop(0)
            
            # Parse horizontal lidars for obstacle mapping
            if dz > 0.2:
                sensors = [
                    ("forward", 0.0),
                    ("right", 90.0),
                    ("left", -90.0)
                ]
                for name, offset in sensors:
                    dist = lidar_distances[name]
                    if 0.3 < dist < 25.0:
                        angle_rad = math.radians(bearing + offset)
                        obs_x = dx + dist * math.cos(angle_rad)
                        obs_y = dy + dist * math.sin(angle_rad)
                        
                        cell_x = round(obs_x * 4) / 4.0
                        cell_y = round(obs_y * 4) / 4.0
                        occupied_cells.add((cell_x, cell_y))
                        obstacles_data.add((cell_x, cell_y))
            
            # Update current drone entry in drones_data
            drones_data[drone_id] = {
                "x": round(dx, 2),
                "y": round(dy, 2),
                "z": round(dz, 2),
                "bearing": bearing,
                "trajectory": trajectory_points
            }
            
            # Write back using exclusive lock
            map_data = {
                "drones": drones_data,
                "obstacles": [[x, y] for x, y in occupied_cells.union(obstacles_data)],
                "origin": origin_data
            }
            
            # Support fallback legacy keys for single drone view
            map_data["drone_x"] = round(dx, 2)
            map_data["drone_y"] = round(dy, 2)
            map_data["drone_z"] = round(dz, 2)
            map_data["drone_bearing"] = bearing
            map_data["trajectory"] = trajectory_points
            
            with open(map_file, "a+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                f.truncate()
                json.dump(map_data, f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
        except Exception as e:
            print(f"[SLAM Error] Mapper thread exception: {e}")
            
        time.sleep(0.2)

def main():
    global stop_requested, is_executing_command

    threading.Thread(target=update_status, daemon=True).start()
    threading.Thread(target=monitor_abort_fifo, daemon=True).start()
    threading.Thread(target=offboard_heartbeat, daemon=True).start()
    threading.Thread(target=run_slam_mapper, daemon=True).start()
    
    while True:
        stop_requested = False  # Reset stop_requested before each new command set
        with open(command_fifo_path, 'r') as fifo:
            # Read a line (message) from the FIFO
            command_string = fifo.readline().strip()
        commands = command_string.split()
        for command in commands:
            if stop_requested:
                break  # Exit the current loop if stop is requested
            print(f"Executing command: {command}")
            is_executing_command = True
            try:
                result = execute_command(command)
            finally:
                is_executing_command = False
            if result == 'stop':
                break

if __name__ == "__main__":
    main()



'''

qhyhu jrqqd jlyh x xs
qhyhu jrqqd ohw brx grzq
qhyhu jrqqd uxq durxqg dqg

ghvvhuw brx

'''