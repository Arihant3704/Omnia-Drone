import streamlit as st
import os
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import math

# 1. Config & Styling
st.set_page_config(
    page_title="Omnia SAR Mission Control",
    page_icon="🛸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Dark UI
st.markdown("""
<style>
    body {
        background-color: #0b0c10;
        color: #c5c6c7;
    }
    .main-header {
        font-family: 'Outfit', sans-serif;
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(45deg, #1f2833, #66fcf1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding-bottom: 20px;
        margin-bottom: 30px;
        border-bottom: 2px solid #1f2833;
    }
    .metric-card {
        background-color: #1f2833;
        border: 1px solid #45a29e;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #66fcf1;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #c5c6c7;
        text-transform: uppercase;
    }
    .status-active {
        color: #66fcf1;
        font-weight: bold;
    }
    .status-inactive {
        color: #ff4b4b;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 2. State loading helper
STATE_FILE = "/tmp/omnia_dashboard_state.json"
FRAME_FILE = "/tmp/omnia_current_frame.jpg"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

state = load_state()

# 3. Sidebar Setup
st.sidebar.markdown("<h2 style='text-align: center; color: #66fcf1;'>🛸 OMNIA PILOT</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# Active status indicator
is_active = state is not None and (time.time() - os.path.getmtime(STATE_FILE) < 30)
if is_active:
    st.sidebar.markdown("Status: <span class='status-active'>🟢 ONLINE (ACTIVE)</span>", unsafe_allow_html=True)
else:
    st.sidebar.markdown("Status: <span class='status-inactive'>🔴 OFFLINE (STALE)</span>", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Live Metrics inside Sidebar
if state:
    telemetry = state.get("telemetry", {})
    st.sidebar.subheader("📡 Live Telemetry")
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        st.metric(label="Altitude", value=f"{telemetry.get('altitude', 0.0):.2f} m")
    with col_b:
        st.metric(label="Bearing", value=f"{telemetry.get('bearing', 0)}°")
        
    st.sidebar.metric(label="Latitude", value=f"{telemetry.get('latitude', 0.0):.7f}")
    st.sidebar.metric(label="Longitude", value=f"{telemetry.get('longitude', 0.0):.7f}")

# Autonomous Mission Dispatch Panel
st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Mission Dispatch Center")
mission_option = st.sidebar.selectbox(
    "Select Mission Profile",
    ["Courier Mode (Office ⇄ Home)", "Search & Rescue (Life Jacket Drop)", "Emergency Medical Delivery"]
)

mission_mapping = {
    "Courier Mode (Office ⇄ Home)": "COURIER",
    "Search & Rescue (Life Jacket Drop)": "SAR_RESCUE",
    "Emergency Medical Delivery": "MEDICAL"
}

col_m1, col_m2 = st.sidebar.columns(2)
with col_m1:
    btn_dispatch = st.button("Dispatch", use_container_width=True)
with col_m2:
    btn_abort = st.button("Abort", use_container_width=True)

if btn_dispatch:
    m_type = mission_mapping[mission_option]
    try:
        with open("/tmp/omnia_active_mission.json", "w") as f:
            json.dump({"mission": m_type, "command": "START", "timestamp": time.time()}, f)
        st.sidebar.success(f"Dispatched: {m_type}")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

if btn_abort:
    try:
        with open("/tmp/omnia_active_mission.json", "w") as f:
            json.dump({"mission": None, "command": "ABORT", "timestamp": time.time()}, f)
        st.sidebar.warning("Sent Abort signal!")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Auto-refresh interval settings
st.sidebar.markdown("---")
auto_refresh = st.sidebar.checkbox("Auto-Refresh Data", value=True)
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 1, 5, 2)

# 4. Main Body Content
st.markdown("<h1 class='main-header'>OMNIA Search & Rescue Mission Control</h1>", unsafe_allow_html=True)

# Display active mission state banner
if state and state.get("mission_mode"):
    mode = state.get("mission_mode")
    phase = state.get("mission_phase", "N/A")
    payload = state.get("payload_status", "N/A")
    alert = state.get("alert_message", "")
    
    st.markdown(f"""
    <div style="background-color: #1f2833; border: 2px solid #66fcf1; border-radius: 10px; padding: 15px; margin-bottom: 20px;">
        <h4 style="color: #66fcf1; margin-top: 0;">🚀 ACTIVE MISSION: {mode}</h4>
        <p style="margin-bottom: 5px;"><b>Current Phase:</b> <span style="color: #45a29e;">{phase}</span></p>
        <p style="margin-bottom: 5px;"><b>Payload Status:</b> <span style="color: #45a29e;">{payload}</span></p>
        <p style="margin-bottom: 0; color: #ff4b4b; font-size: 1.1rem; font-weight: bold;">⚠️ Alert: {alert}</p>
    </div>
    """, unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 1, 1])

# Column 1: Live FPV Feed
with col1:
    st.markdown("<h3 style='color: #66fcf1;'>👁️ Onboard Camera Feed (YOLO Overlay)</h3>", unsafe_allow_html=True)
    if os.path.exists(FRAME_FILE):
        try:
            image = Image.open(FRAME_FILE)
            st.image(image, use_column_width=True)
        except Exception as e:
            st.error(f"Error loading frame: {e}")
    else:
        st.info("Waiting for live video feed to start...")

# Column 2: Real-time 2D SLAM Map
with col2:
    st.markdown("<h3 style='color: #66fcf1;'>🔌 Real-time 2D SLAM Map</h3>", unsafe_allow_html=True)
    MAP_FILE = "/tmp/omnia_map.json"
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, "r") as f:
                map_data = json.load(f)
            
            obstacles = map_data.get("obstacles", [])
            drones = map_data.get("drones", {})
            
            # Fallback to single drone legacy formatting if drones dict is missing
            if not drones:
                drones = {
                    "drone_1": {
                        "x": map_data.get("drone_x", 0.0),
                        "y": map_data.get("drone_y", 0.0),
                        "z": map_data.get("drone_z", 0.0),
                        "bearing": map_data.get("drone_bearing", 0.0),
                        "trajectory": map_data.get("trajectory", [])
                    }
                }
            
            fig_slam = go.Figure()
            
            # 1. Plot Mapped Obstacles (occupied cells)
            if obstacles:
                obs_x = [o[1] for o in obstacles]  # East (y offset)
                obs_y = [o[0] for o in obstacles]  # North (x offset)
                fig_slam.add_trace(go.Scatter(
                    x=obs_x,
                    y=obs_y,
                    mode='markers',
                    name='Obstacles',
                    marker=dict(
                        size=6,
                        color='#c5c6c7',
                        symbol='square',
                        opacity=0.8
                    )
                ))
            
            # Drone visual configurations
            drone_colors = {
                "drone_1": {"body": "#ff4b4b", "path": "#45a29e", "dash": "dot"},
                "drone_2": {"body": "#ffaa00", "path": "#d4a373", "dash": "dash"},
                "drone_3": {"body": "#00ff66", "path": "#588157", "dash": "dashdot"},
                "drone_4": {"body": "#00aaff", "path": "#3a86c8", "dash": "solid"}
            }
            default_color = {"body": "#ff4b4b", "path": "#45a29e", "dash": "dot"}
            
            for d_id, d_info in drones.items():
                color_cfg = drone_colors.get(d_id, default_color)
                dx = d_info.get("x", 0.0)
                dy = d_info.get("y", 0.0)
                bearing = d_info.get("bearing", 0.0)
                traj = d_info.get("trajectory", [])
                
                # 2. Plot Drone Trajectory
                if traj:
                    traj_x = [t[1] for t in traj]
                    traj_y = [t[0] for t in traj]
                    fig_slam.add_trace(go.Scatter(
                        x=traj_x,
                        y=traj_y,
                        mode='lines',
                        name=f'{d_id} Path',
                        line=dict(color=color_cfg["path"], width=2, dash=color_cfg["dash"])
                    ))
                    
                # 3. Plot Drone Current Position
                fig_slam.add_trace(go.Scatter(
                    x=[dy],
                    y=[dx],
                    mode='markers',
                    name=f'{d_id}',
                    marker=dict(
                        size=12,
                        color=color_cfg["body"],
                        symbol='circle'
                    )
                ))
                
                # 4. Plot Drone Heading Line
                heading_len = 2.0
                heading_rad = math.radians(bearing)
                pointer_y = dx + heading_len * math.cos(heading_rad)
                pointer_x = dy + heading_len * math.sin(heading_rad)
                
                fig_slam.add_trace(go.Scatter(
                    x=[dy, pointer_x],
                    y=[dx, pointer_y],
                    mode='lines',
                    name=f'{d_id} Head',
                    line=dict(color=color_cfg["body"], width=3)
                ))
            
            fig_slam.update_layout(
                paper_bgcolor='#1f2833',
                plot_bgcolor='#0b0c10',
                font_color='#c5c6c7',
                xaxis_title="East (Y offset, m)",
                yaxis_title="North (X offset, m)",
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=True,
                xaxis=dict(gridcolor='#1f2833', zeroline=True, zerolinecolor='#66fcf1'),
                yaxis=dict(gridcolor='#1f2833', zeroline=True, zerolinecolor='#66fcf1'),
                height=350,
                yaxis_scaleanchor="x"
            )
            st.plotly_chart(fig_slam, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading SLAM map: {e}")
    else:
        st.info("Waiting for SLAM mapping data...")

# Column 3: Plotly Live Trajectory Path
with col3:
    st.markdown("<h3 style='color: #66fcf1;'>📍 Cooperative Trajectory Map</h3>", unsafe_allow_html=True)
    
    # Retrieve cooperative drones from shared memory
    memories = state.get("memories", {}) if state else {}
    active_drones = memories.get("active_drones", {}) if memories else {}
    
    # Fallback to single drone legacy formatting if active_drones is empty
    if not active_drones and state and state.get("history"):
        active_drones = {
            "drone_1": {
                "latitude": telemetry.get("latitude", 0),
                "longitude": telemetry.get("longitude", 0),
                "status": state.get("mission_mode", "IDLE"),
                "phase": state.get("mission_phase", "IDLE"),
                "trajectory": state.get("history", [])
            }
        }
        
    if active_drones:
        fig = go.Figure()
        
        drone_colors = {
            "drone_1": {"body": "#ff4b4b", "path": "#45a29e", "dash": "solid"},
            "drone_2": {"body": "#ffaa00", "path": "#d4a373", "dash": "dash"},
            "drone_3": {"body": "#00ff66", "path": "#588157", "dash": "dashdot"},
            "drone_4": {"body": "#00aaff", "path": "#3a86c8", "dash": "dot"}
        }
        default_color = {"body": "#ff4b4b", "path": "#45a29e", "dash": "solid"}
        
        for d_id, d_info in active_drones.items():
            color_cfg = drone_colors.get(d_id, default_color)
            traj = d_info.get("trajectory", [])
            
            if traj:
                df = pd.DataFrame(traj)
                fig.add_trace(go.Scatter(
                    x=df['longitude'],
                    y=df['latitude'],
                    mode='lines+markers',
                    name=f'{d_id} Path',
                    line=dict(color=color_cfg["path"], width=3, dash=color_cfg["dash"]),
                    marker=dict(size=5, color=color_cfg["path"])
                ))
            
            # Current Position marker
            current_lat = d_info.get('latitude', 0)
            current_lon = d_info.get('longitude', 0)
            status_info = f"{d_id} ({d_info.get('status', 'IDLE')})"
            
            fig.add_trace(go.Scatter(
                x=[current_lon],
                y=[current_lat],
                mode='markers',
                name=status_info,
                marker=dict(size=12, color=color_cfg["body"], line=dict(color='white', width=1.5))
            ))
            
        fig.update_layout(
            paper_bgcolor='#1f2833',
            plot_bgcolor='#0b0c10',
            font_color='#c5c6c7',
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            margin=dict(l=20, r=20, t=20, b=20),
            showlegend=True,
            xaxis=dict(gridcolor='#1f2833', zeroline=False),
            yaxis=dict(gridcolor='#1f2833', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Waiting for coordinate history data...")

# 5. Active Memory & ReAct Trace Audit Section
st.markdown("---")
col_react, col_mem = st.columns([1, 1])

with col_react:
    st.markdown("<h3 style='color: #66fcf1;'>🧠 Agentic ReAct Reasoning Trace</h3>", unsafe_allow_html=True)
    if state:
        st.subheader("⚙️ Executed Command")
        action = state.get("action", "NONE").upper()
        action_data = state.get("action_data", {})
        if action != "NONE":
            st.success(f"**Action**: `{action}`  \n**Details**: `{action_data}`")
        else:
            st.warning("No command executed yet (Hovering).")
            
        st.subheader("🎯 Detections & perception")
        detections = state.get("detections", [])
        if detections:
            st.info(", ".join([f"🎯 {d}" for d in detections]))
        else:
            st.info("No targets detected in current view.")
            
        st.subheader("📖 Visual Scene Report")
        st.write(state.get("scene_description", "N/A"))
        
        with st.expander("🔍 Complete Cognitive Process"):
            st.code(state.get("thinking", "N/A"), language="json")
    else:
        st.info("No active agent reasoning traces found.")

with col_mem:
    st.markdown("<h3 style='color: #66fcf1;'>💾 Pilot Persistent Memory Base</h3>", unsafe_allow_html=True)
    tab_general, tab_remembr = st.tabs(["📋 General Memory & SOPs", "🧠 NVIDIA ReMEmbR Vector DB"])
    
    with tab_general:
        if state and "memories" in state:
            memories = state.get("memories", {})
            
            # --- Cooperative Fleet Status ---
            st.subheader("👥 Cooperative Fleet Status")
            active_drones = memories.get("active_drones", {})
            if active_drones:
                fleet_data = []
                for d_id, d_info in active_drones.items():
                    elapsed = time.time() - d_info.get("last_update", time.time())
                    fleet_data.append({
                        "Drone ID": d_id,
                        "Latitude": f"{d_info.get('latitude', 0):.6f}",
                        "Longitude": f"{d_info.get('longitude', 0):.6f}",
                        "Altitude": f"{d_info.get('altitude', 0):.2f}m",
                        "Status": d_info.get("status", "IDLE"),
                        "Phase": d_info.get("phase", "IDLE"),
                        "Last Seen": f"{elapsed:.1f}s ago"
                    })
                st.table(pd.DataFrame(fleet_data))
            else:
                st.info("No active cooperative agents registered.")
                
            # --- SLAM Mapped Landmarks ---
            st.subheader("📍 SLAM Mapped Landmarks")
            landmarks = memories.get("detected_landmarks", {})
            if landmarks:
                lm_data = []
                for name, info in landmarks.items():
                    if isinstance(info, dict):
                        lm_data.append({
                            "Landmark": name.upper(),
                            "X": info.get("x"),
                            "Y": info.get("y"),
                            "Detected By": info.get("detected_by", "unknown"),
                            "Age": f"{time.time() - info.get('timestamp', time.time()):.1f}s ago" if "timestamp" in info else "N/A"
                        })
                    else:
                        lm_data.append({
                            "Landmark": name.upper(),
                            "X": info[0] if isinstance(info, list) else info,
                            "Y": info[1] if isinstance(info, list) else info,
                            "Detected By": "legacy",
                            "Age": "N/A"
                        })
                st.table(pd.DataFrame(lm_data))
            else:
                st.info("No landmarks mapped by SLAM yet.")
            
            st.subheader("🧠 Stored Environmental Facts")
            facts = memories.get("saved_facts", [])
            if facts:
                for fact in facts:
                    st.markdown(f"- 📌 {fact}")
            else:
                st.info("No facts saved to persistent memory yet.")
                
            st.subheader("🗺️ Quadrant Scenery Knowledge")
            quads = memories.get("quadrants", {})
            for q_name, q_desc in quads.items():
                st.markdown(f"**{q_name}**: {q_desc}")
                
            st.subheader("📍 Registered Waypoints")
            locs = memories.get("locations", {})
            locs_df = pd.DataFrame([{"Waypoint": k.upper(), "X Coordinate": v["x"], "Y Coordinate": v["y"]} for k, v in locs.items()])
            st.table(locs_df)
            
            st.subheader("📋 Active SOP Guidelines (RAG)")
            retrieved_sop = state.get("retrieved_sop", [])
            if retrieved_sop:
                for chunk in retrieved_sop:
                    st.markdown(f"```markdown\n{chunk}\n```")
            else:
                st.info("No active SOP guidelines retrieved.")
      
            st.subheader("🧠 Reflection & Learning Logs")
            lessons = memories.get("lessons_learned", [])
            if lessons:
                for l in reversed(lessons):
                    d_prefix = f"[{l.get('drone_id', 'legacy').upper()}] "
                    st.markdown(f"**{d_prefix}[{l['action'].upper()}]** ({l['timestamp'].split('T')[1][:8]}): {l['outcome']}")
            else:
                st.info("No reflection logs recorded yet.")
        else:
            st.info("Waiting for agent to initialize memory system...")

    with tab_remembr:
        # Load local ReMEmbR module to allow in-dashboard semantic search
        try:
            import sys
            if "/home/arihant/simulation/core" not in sys.path:
                sys.path.append("/home/arihant/simulation/core")
            from remembr_memory import ReMEmbRMemory
            remembr_db = ReMEmbRMemory(db_path="/tmp/omnia_remembr.json")
        except Exception as e:
            remembr_db = None
            st.error(f"Could not load ReMEmbR memory engine: {e}")

        if remembr_db and remembr_db.memories:
            summary = remembr_db.get_memory_summary()
            
            # KPI Metrics Row
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric("Spatio-Temporal Memories", summary["total_memories"])
            with m_col2:
                st.metric("Time Span Logged", f"{summary['time_span_minutes']} mins")
            with m_col3:
                st.metric("Unique Classes Mapped", len(summary["unique_detections"]))
            
            # Semantic search query box
            st.subheader("🔍 Semantic Vector Search")
            search_query = st.text_input("Enter search phrase (e.g. 'fallen person', 'red toolbox')", key="remembr_search")
            if search_query:
                with st.spinner("Searching vector embeddings..."):
                    search_results = remembr_db.query_by_text(search_query, top_k=5)
                if search_results:
                    for mem, score in search_results:
                        t_ago = (time.time() - mem['timestamp']) / 60
                        st.markdown(f"""
                        <div style='background-color: #1f2833; border-left: 5px solid #66fcf1; padding: 10px; border-radius: 4px; margin-bottom: 8px;'>
                            <span style='color: #66fcf1; font-weight: bold;'>[Match Score: {score:.2f}]</span> 
                            <strong>Drone:</strong> {mem['drone_id']} | 
                            <strong>XY Location:</strong> ({mem['local_xy']['x']:.1f}, {mem['local_xy']['y']:.1f}) | 
                            <strong>Time:</strong> {t_ago:.1f} mins ago
                            <p style='margin: 5px 0 0 0; color: #c5c6c7;'>"{mem['caption']}"</p>
                            <span style='font-size: 0.85em; color: #45a29e;'>Detections: {', '.join(mem['detections']) if mem['detections'] else 'None'}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No matching memories found.")
            
            # Memory Timeline Stream
            st.subheader("🕰️ Spatio-Temporal Memory Timeline (Latest first)")
            for mem in reversed(remembr_db.memories[-10:]):
                t_ago = (time.time() - mem['timestamp']) / 60
                st.markdown(f"""
                <div style='background-color: #0b0c10; border: 1px solid #1f2833; padding: 12px; border-radius: 6px; margin-bottom: 8px;'>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #45a29e; font-weight: bold;'>{mem['id'].upper()}</span>
                        <span style='color: #888;'>{t_ago:.1f} mins ago</span>
                    </div>
                    <p style='margin: 8px 0; font-style: italic; color: #fff;'>"{mem['caption']}"</p>
                    <div style='font-size: 0.9em; display: flex; gap: 15px; color: #c5c6c7;'>
                        <span>📍 <b>Local XY:</b> ({mem['local_xy']['x']:.1f}, {mem['local_xy']['y']:.1f})</span>
                        <span>🧭 <b>Heading:</b> {mem['bearing']:.1f}°</span>
                        <span>📈 <b>Altitude:</b> {mem['altitude']:.1f}m</span>
                    </div>
                    {f"<div style='margin-top: 5px;'><span style='background-color: #1f2833; color: #66fcf1; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;'>🏷️ {', '.join(mem['detections'])}</span></div>" if mem['detections'] else ""}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No spatio-temporal memories recorded in vector database yet.")

# 6. Interactive Operator Controls & Quick Coordinates Actions
st.markdown("---")
col_input_sec, col_quick_sec = st.columns([3, 2])

with col_input_sec:
    st.markdown("<h3 style='color: #66fcf1;'>💬 Dynamic Operator Console</h3>", unsafe_allow_html=True)
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        user_cmd = st.text_input("Send Dynamic Instruction to AI Pilot (e.g., 'fly to hospital', 'remember to record debris')", key="chat_input", label_visibility="collapsed")
    with col_btn:
        btn_click = st.button("Send Instruction", use_container_width=True)
    
    if btn_click and user_cmd.strip():
        try:
            with open("/tmp/omnia_user_instruction.json", "w") as f:
                json.dump({"instruction": user_cmd.strip(), "timestamp": time.time(), "processed": False}, f)
            st.success(f"Sent instruction: '{user_cmd}'")
        except Exception as e:
            st.error(f"Error sending instruction: {e}")

with col_quick_sec:
    st.markdown("<h3 style='color: #66fcf1;'>⚡ Quick Navigation Overrides</h3>", unsafe_allow_html=True)
    st.markdown("Instantly override the current routine to send the drone to mapped coordinates:")
    
    q_col1, q_col2, q_col3 = st.columns(3)
    
    with q_col1:
        if st.button("Fly to Home (Q4)", use_container_width=True):
            try:
                with open("/tmp/omnia_user_instruction.json", "w") as f:
                    json.dump({"instruction": "fly to home", "timestamp": time.time(), "processed": False}, f)
                st.success("Wrote: fly to home")
            except Exception as e:
                st.error(str(e))
    with q_col2:
        if st.button("Fly to Hospital (Q4)", use_container_width=True):
            try:
                with open("/tmp/omnia_user_instruction.json", "w") as f:
                    json.dump({"instruction": "fly to hospital", "timestamp": time.time(), "processed": False}, f)
                st.success("Wrote: fly to hospital")
            except Exception as e:
                st.error(str(e))
    with q_col3:
        if st.button("Return to Base", use_container_width=True):
            try:
                with open("/tmp/omnia_user_instruction.json", "w") as f:
                    json.dump({"instruction": "fly to origin", "timestamp": time.time(), "processed": False}, f)
                st.success("Wrote: fly to origin")
            except Exception as e:
                st.error(str(e))

# Auto-refresh loop logic
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
