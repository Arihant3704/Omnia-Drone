#!/bin/bash
set -e

echo "Starting PX4 Autopilot Toolchain installation for Ubuntu 22.04..."

# 1. Clone the PX4 Autopilot repository if it doesn't exist
if [ ! -d "PX4-Autopilot" ]; then
    echo "Cloning PX4-Autopilot repository..."
    git clone https://github.com/PX4/PX4-Autopilot.git --recursive
fi

# 2. Run the official setup script
# Note: This will request sudo password and might take 10-20 minutes.
echo "Running PX4 setup script (this installs Gazebo, Toolchain, and dependencies)..."
bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx

echo "Installation script finished. Please restart your shell or run 'source ~/.bashrc' before using PX4."
