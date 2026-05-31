#!/bin/bash

echo "=========================================="
echo " Stopping OMNIA SAR Simulation & Agents"
echo "=========================================="

# 1. Kill all python agents, controller, and dashboard processes
echo "[1/3] Terminating Python agents and Streamlit dashboard..."
pkill -9 -f "controller.py|agent_pilot|streamlit|dashboard.py" 2>/dev/null || true

# 2. Kill PX4 SITL and Gazebo Classic simulation
echo "[2/3] Terminating PX4 SITL and Gazebo simulation..."
pkill -9 -f "px4|gazebo|gzserver|gzclient" 2>/dev/null || true

# 3. Clean up IPC pipes and temporary JSON states
echo "[3/3] Cleaning up IPC files and temporary states..."
rm -f /tmp/gpt_command_fifo /tmp/gpt_status_fifo /tmp/gpt_abort_fifo /tmp/gpt_statusa_fifo
rm -f /tmp/omnia_active_mission.json /tmp/omnia_dashboard_state.json /tmp/omnia_user_instruction.json

echo "------------------------------------------"
echo " Cleanup complete! All simulation processes stopped."
echo " Note: The Ollama service will automatically unload models"
echo "       from GPU VRAM after 5 minutes of inactivity."
echo "       To force-stop Ollama immediately, run:"
echo "       sudo systemctl stop ollama"
echo "=========================================="
