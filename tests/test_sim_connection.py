import asyncio
from mavsdk import System
import logging

async def test_sim_connection():
    logging.basicConfig(level=logging.INFO)
    drone = System()
    print("Attempting to connect to PX4 SITL (udp://:14540)...")
    
    try:
        # Timeout after 10 seconds
        await asyncio.wait_for(drone.connect(system_address="udp://:14540"), timeout=10)
        
        async for state in drone.core.connection_state():
            if state.is_connected:
                print("SUCCESS: Connected to simulation!")
                break
                
        print("Fetching battery telemetry as a test...")
        async for battery in drone.telemetry.battery():
            print(f"Battery: {battery.remaining_percent * 100:.1f}%")
            break
            
    except asyncio.TimeoutError:
        print("FAILED: Could not connect to simulation. Is PX4 SITL running?")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_sim_connection())
