#!/bin/bash

# 1. Setup Environment
source "$HOME/simulation/.env" # Assuming API key is here
export GOOGLE_API_KEY

# 2. Path to the core directory of your existing project
CORE_DIR="$HOME/simulation/core"
cd "$CORE_DIR"

echo "Cleaning up previous IPC pipes..."
rm -f /tmp/gpt_command_fifo /tmp/gpt_status_fifo

echo "Starting PolluxPenguin Simulation Components (PX4 SITL with Gazebo)..."
# Start PX4 SITL (standard iris drone on Gazebo Classic)
gnome-terminal --tab -- bash -c "cd ~/simulation/PX4-Autopilot && export PX4_PARAM_COM_LOW_BAT_ACT=0 && export PX4_PARAM_SIM_BAT_DRAIN=0 && export PX4_PARAM_COM_RCL_EXCEPT=31 && export PX4_PARAM_COM_OF_LOSS_T=86400 && make px4_sitl gazebo-classic_iris_depth_camera; exec $SHELL" &
sleep 25

# Start the Legacy Controller (The bridge to MAVLink)
gnome-terminal --tab -- bash -c "python3 controller.py; exec $SHELL" &
sleep 2

echo "Starting NEW Omnia Agentic Pilot (Gemini 3.1 Mode)..."
# Launch the verified Pseudo-Live agent
gnome-terminal --tab -- bash -c "python3 agent_pilot_pseudolive.py; exec $SHELL" &

# Optional: Start web server if you still want the dashboard logs
cd "../webApp"
gnome-terminal --tab -- bash -c "node server.js; exec $SHELL" &

echo "Omnia-Pilot is live. Use voice commands to begin the 'Semantic First Responder' mission."
