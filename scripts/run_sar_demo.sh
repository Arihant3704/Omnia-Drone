#!/bin/bash

# =============================================
# OMNIA SAR Demo Launcher
# Search and Rescue Drone Simulation
# =============================================

# 1. Setup Environment
source "$HOME/simulation/.env"
export GOOGLE_API_KEY

CORE_DIR="$HOME/simulation/core"
PX4_DIR="$HOME/simulation/PX4-Autopilot"
cd "$CORE_DIR"

echo "=========================================="
echo "  OMNIA - Search and Rescue Demo"
echo "=========================================="

echo "[1/4] Cleaning up previous IPC pipes..."
rm -f /tmp/gpt_command_fifo /tmp/gpt_status_fifo /tmp/gpt_abort_fifo /tmp/gpt_statusa_fifo

echo "[2/4] Starting PX4 SITL with SAR Demo World..."
# Launch PX4 SITL with the custom SAR warehouse world
gnome-terminal --tab --title="PX4 SITL" -- bash -c "
  cd $PX4_DIR && \
  export GAZEBO_MODEL_DATABASE_URI='' && \
  export PX4_PARAM_COM_LOW_BAT_ACT=0 && \
  export PX4_PARAM_SIM_BAT_DRAIN=0 && \
  export PX4_PARAM_COM_RCL_EXCEPT=31 && \
  export PX4_PARAM_COM_OF_LOSS_T=86400 && \
  PX4_SITL_WORLD=sar_demo make px4_sitl gazebo-classic_iris_downward_depth_camera 2>&1 | tee /tmp/px4_sitl.log; \
  exec \$SHELL" &
sleep 25

echo "[3/4] Starting Drone Controller..."
gnome-terminal --tab --title="Controller" -- bash -c "
  cd $CORE_DIR && \
  python3 -u controller.py 2>&1 | tee /tmp/omnia_controller.log; \
  exec \$SHELL" &
sleep 2

echo "[4/5] Starting Omnia Agentic Pilot..."
gnome-terminal --tab --title="Omnia Pilot" -- bash -c "
  cd $CORE_DIR && \
  python3 -u agent_pilot_pseudolive.py 2>&1 | tee /tmp/omnia_pilot.log; \
  exec \$SHELL" &
sleep 2

echo "[5/5] Starting Omnia Mission Dashboard..."
gnome-terminal --tab --title="Omnia Dashboard" -- bash -c "
  cd $CORE_DIR && \
  streamlit run dashboard.py --server.port 8501 2>&1 | tee /tmp/omnia_dashboard.log; \
  exec \$SHELL" &

echo ""
echo "=========================================="
echo "  SAR Demo Environment Ready!"
echo ""
echo "  Targets placed in warehouse:"
echo "    - 3 Persons (injured/trapped)"
echo "    - 2 Red Toolboxes"
echo "    - 2 Safety Vests"
echo "    - 1 Blue Car (loading dock)"
echo "    - Scattered debris"
echo ""
echo "  Dashboard: http://localhost:8501"
echo ""
echo "  Use the command FIFO to control:"
echo "    echo 'F5' > /tmp/gpt_command_fifo"
echo "    echo 'LAND' > /tmp/gpt_command_fifo"
echo "=========================================="
