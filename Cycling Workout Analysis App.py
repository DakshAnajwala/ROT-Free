"""
app.py  —  Cycling Performance Analyser
Run with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import anthropic
import datetime
import os

from fit_parser import parse_fit, SessionData
from analytics import (
    compute, RideAnalytics, build_coach_prompt,
    DEFAULT_HR_ZONES, ZONE_COLORS, POWER_ZONE_NAMES, power_zones_from_ftp,
)
from history import load_history, save_session, delete_session

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cycling Performance Analyser",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Font import */
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;900&family=Barlow:wght@300;400;500&display=swap');

  /* Global */
  html, body, [class*="css"] { font-family: 'Barlow', sans-serif; }

  /* Hide Streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

  /* App header */
  .app-header {
    background: linear-gradient(135deg, #0d0d0d 0%, #1a1a1a 100%);
    border-bottom: 3px solid #E8001D;
    padding: 1.2rem 1.5rem 1rem;
    margin: -1.5rem -1rem 1.5rem;
    display: flex; align-items: center; gap: 16px;
  }
  .app-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem; font-weight: 900;
    color: #fff; letter-spacing: -0.5px; margin: 0;
    text-transform: uppercase;
  }
  .app-title span { color: #E8001D; }
  .app-subtitle {
    font-size: 0.75rem; letter-spacing: 3px;
    text-transform: uppercase; color: #888; margin-top: 2px;
  }

  /* Metric cards */
  .metric-card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    padding: 1rem 1.2rem;
    border-left: 3px solid #E8001D;
  }
  .metric-label {
    font-size: 0.65rem; letter-spacing: 2px;
    text-transform: uppercase; color: #888; margin-bottom: 4px;
  }
  .metric-value {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem; font-weight: 700; color: #fff; line-height: 1;
  }
  .metric-unit { font-size: 1rem; font-weight: 400; color: #666; }
  .metric-sub { font-size: 0.7rem; color: #666; margin-top: 4px; }

  /* Section headers */
  .section-head {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.1rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: #E8001D; border-bottom: 1px solid #2a2a2a;
    padding-bottom: 6px; margin: 1.5rem 0 1rem;
  }

  /* Coach card */
  .coach-card {
    background: #111;
    border: 1px solid #222;
    border-top: 3px solid #E8001D;
    border-radius: 4px;
    padding: 1.5rem;
    margin-top: 1rem;
  }

  /* Zone badge */
  .zone-badge {
    display: inline-block;
    font-size: 0.65rem; font-weight: 700;
    letter-spacing: 1.5px; text-transform: uppercase;
    padding: 2px 7px; border-radius: 2px; margin-right: 6px;
  }

  /* Lap table */
  .lap-table th { font-size: 0.7rem !important; }

  /* Sidebar styling */
  [data-testid="stSidebar"] {
    background: #111 !important;
    border-right: 1px solid #222;
  }
  [data-testid="stSidebar"] .stSlider label,
  [data-testid="stSidebar"] .stNumberInput label,
  [data-testid="stSidebar"] .stSelectbox label { color: #aaa !important; font-size: 0.8rem; }

  /* Plotly charts dark background */
  .js-plotly-plot { border-radius: 4px; }

  /* Upload zone */
  [data-testid="stFileUploader"] {
    border: 2px dashed #333 !important;
    border-radius: 8px !important;
    background: #111 !important;
  }
  [data-testid="stFileUploader"]:hover { border-color: #E8001D !important; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #2a2a2a; }
  .stTabs [data-baseweb="tab"] {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 0.85rem !important; font-weight: 700 !important;
    letter-spacing: 1.5px !important; text-transform: uppercase !important;
    color: #888 !important; padding: 6px 16px !important;
    border: none !important; background: transparent !important;
  }
  .stTabs [aria-selected="true"] {
    color: #E8001D !important;
    border-bottom: 2px solid #E8001D !important;
  }

  /* Streamlit button */
  .stButton > button {
    background: #E8001D !important; color: #fff !important;
    border: none !important; border-radius: 3px !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 700 !important; letter-spacing: 2px !important;
    text-transform: uppercase !important; font-size: 0.85rem !important;
    padding: 0.4rem 1.2rem !important;
  }
  .stButton > button:hover { background: #c0001a !important; }

  /* History table */
  .history-row {
    background: #1a1a1a; border: 1px solid #252525;
    border-radius: 3px; padding: 10px 14px; margin-bottom: 4px;
    display: flex; align-items: center; gap: 16px;
  }
</style>
""", unsafe_allow_html=True)

# ── Plotly dark theme helper ───────────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="#111",
    plot_bgcolor="#111",
    font=dict(family="Barlow, sans-serif", color="#aaa", size=11),
    xaxis=dict(gridcolor="#222", zerolinecolor="#222", linecolor="#333"),
    yaxis=dict(gridcolor="#222", zerolinecolor="#222", linecolor="#333"),
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(bgcolor="#1a1a1a", bordercolor="#333", borderwidth=1),
    hovermode="x unified",
)


def apply_dark(fig):
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_xaxes(gridcolor="#222", linecolor="#333")
    fig.update_yaxes(gridcolor="#222", linecolor="#333")
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Rider Settings")
    st.markdown("---")

    weight_kg = st.number_input("Body Weight (kg)", min_value=40.0, max_value=150.0,
                                 value=float(st.session_state.get("weight_kg", 70.0)),
                                 step=0.5, key="weight_kg")

    ftp = st.number_input("FTP — Functional Threshold Power (W)",
                           min_value=50, max_value=600,
                           value=int(st.session_state.get("ftp", 200)),
                           step=5, key="ftp")

    st.markdown(f"**FTP:** {ftp/weight_kg:.2f} W/kg")

    st.markdown("---")
    st.markdown("### 💓 HR Zones (bpm)")

    hr_zones = {}
    zone_defaults = [(100, 120), (120, 150), (150, 165), (165, 185), (185, 220)]
    for i, (lo_d, hi_d) in enumerate(zone_defaults):
        z = f"Z{i+1}"
        c1, c2 = st.columns(2)
        lo = c1.number_input(f"{z} Low", value=lo_d, min_value=50, max_value=250,
                              key=f"hrz_{z}_lo", label_visibility="collapsed")
        hi = c2.number_input(f"{z} High", value=hi_d, min_value=51, max_value=999,
                              key=f"hrz_{z}_hi", label_visibility="collapsed")
        hr_zones[z] = (lo, hi)
    st.caption("Z1 Low — Z1 High / Z2 Low — Z2 High …")

    st.markdown("---")
    st.markdown("### 🤖 AI Coach")
    api_key = st.text_input("Anthropic API Key", type="password",
                             placeholder="sk-ant-...",
                             help="Get yours at console.anthropic.com",
                             key="api_key")
    if api_key:
        st.success("API key set ✓")

    st.markdown("---")
    st.caption("🚴 Cycling Performance Analyser v1.0")


# ── App header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div>
    <div class="app-title">Cycling <span>Analyser</span></div>
    <div class="app-subtitle">Performance Intelligence Platform</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_analyse, tab_history = st.tabs(["📊  Analyse Session", "📋  Training Log"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: ANALYSE SESSION
# ══════════════════════════════════════════════════════════════════════════════
with tab_analyse:

    # ── File upload ───────────────────────────────────────────────────────────
    col_upload, col_info = st.columns([2, 1])
    with col_upload:
        uploaded = st.file_uploader(
            "Upload your .fit file",
            type=["fit"],
            help="Export your .fit file from Garmin Connect, Wahoo, Zwift, or similar.",
        )

    with col_info:
        st.markdown("""
        **Supported devices:**
        - Garmin Edge / Forerunner
        - Wahoo ELEMNT
        - Zwift (export from website)
        - Any ANT+ / Bluetooth head unit
        """)

    if not uploaded:
        # ── Landing state ─────────────────────────────────────────────────────
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### 📂 Upload")
            st.markdown("Drop any `.fit` file from your bike computer or training app.")
        with c2:
            st.markdown("#### 📊 Analyse")
            st.markdown("Power curves, HR zones, cadence, pacing, fatigue — all computed automatically.")
        with c3:
            st.markdown("#### 🤖 AI Coach")
            st.markdown("Add your Anthropic API key for a personalised coach-style analysis.")
        st.stop()

    # ── Parse file ────────────────────────────────────────────────────────────
    file_bytes = uploaded.read()
    with st.spinner("Parsing .fit file…"):
        try:
            sd: SessionData = parse_fit(file_bytes)
        except Exception as e:
            st.error(f"Could not parse file: {e}")
            st.stop()

    ra: RideAnalytics = compute(sd, weight_kg, ftp, hr_zones)

    # ── Session banner ────────────────────────────────────────────────────────
    date_str = sd.start_datetime.strftime("%a %d %b %Y, %H:%M") if sd.start_datetime else "Unknown"
    st.markdown(f"### 📍 {uploaded.name} &nbsp;·&nbsp; <span style='color:#888;font-size:0.9rem;'>{date_str}</span>", unsafe_allow_html=True)

    # ── Key stats row ─────────────────────────────────────────────────────────
    def metric_card(label, value, unit="", sub="", accent="#E8001D"):
        return f"""
        <div class="metric-card" style="border-left-color:{accent}">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}<span class="metric-unit"> {unit}</span></div>
          <div class="metric-sub">{sub}</div>
        </div>"""

    dur_h = int(sd.duration_s // 3600)
    dur_m = int((sd.duration_s % 3600) // 60)
    dur_str = f"{dur_h}h {dur_m:02d}m" if dur_h else f"{dur_m}m"

    cols = st.columns(8)
    cards = [
        ("Duration",     dur_str,                   "",    f"{sd.duration_s/60:.0f} min total",       "#E8001D"),
        ("Distance",     f"{sd.distance_m/1000:.1f}","km", "",                                         "#2979ff"),
        ("Avg Speed",    f"{sd.avg_speed_ms*3.6:.1f}","km/h",f"Max {sd.max_speed_ms*3.6:.1f} km/h",   "#5c85d6"),
        ("Elevation",    f"{sd.total_ascent_m}",     "m",  f"Descent {sd.total_descent_m}m",           "#4caf7d"),
        ("Avg Power",    f"{ra.avg_power:.0f}",      "W",  f"NP {ra.np:.0f}W · {ra.np_wkg:.2f} W/kg", "#f0b429"),
        ("Max Power",    f"{sd.max_power}",          "W",  f"Best 5s: {ra.best_5s:.0f}W",              "#f06529"),
        ("Avg HR",       f"{ra.avg_hr:.0f}",         "bpm",f"Max {ra.max_hr} bpm",                     "#e8001d"),
        ("Avg Cadence",  f"{ra.avg_cadence:.0f}",    "rpm",f"Max {ra.max_cadence} rpm",                "#888"),
    ]
    for col, (label, val, unit, sub, color) in zip(cols, cards):
        col.markdown(metric_card(label, val, unit, sub, color), unsafe_allow_html=True)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # CHARTS
    # ══════════════════════════════════════════════════════════════════════════

    # Build a time axis in minutes
    t_min = [t / 60 for t in sd.timestamps]

    # ── 1. Power + HR overview chart ─────────────────────────────────────────
    st.markdown('<div class="section-head">Power & Heart Rate</div>', unsafe_allow_html=True)

    fig_main = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        subplot_titles=("Power (W)", "Heart Rate (bpm)"),
        row_heights=[0.55, 0.45],
    )

    # Power
    if any(sd.power_ts):
        pwr_clean = [p if p else None for p in sd.power_ts]
        fig_main.add_trace(go.Scatter(
            x=t_min, y=pwr_clean, mode="lines",
            name="Power", line=dict(color="#f0b429", width=1.2),
            fill="tozeroy", fillcolor="rgba(240,180,41,0.08)",
        ), row=1, col=1)

        # NP reference line
        fig_main.add_hline(y=ra.np, line=dict(color="#f06529", dash="dash", width=1),
                           annotation_text=f"NP {ra.np:.0f}W", row=1, col=1)
        fig_main.add_hline(y=ftp, line=dict(color="#E8001D", dash="dot", width=1),
                           annotation_text=f"FTP {ftp}W", row=1, col=1)

    # HR
    if any(sd.hr_ts):
        hr_clean = [h if h else None for h in sd.hr_ts]
        fig_main.add_trace(go.Scatter(
            x=t_min, y=hr_clean, mode="lines",
            name="Heart Rate", line=dict(color="#e8001d", width=1.2),
            fill="tozeroy", fillcolor="rgba(232,0,29,0.06)",
        ), row=2, col=1)

        # HR zone shading
        z_colors_rgba = {
            "Z1": "rgba(92,133,214,0.07)", "Z2": "rgba(76,175,125,0.07)",
            "Z3": "rgba(240,180,41,0.08)", "Z4": "rgba(240,101,41,0.09)", "Z5": "rgba(232,0,29,0.12)",
        }
        for z, (lo, hi) in hr_zones.items():
            fig_main.add_hrect(y0=lo, y1=min(hi, ra.max_hr + 10),
                               fillcolor=z_colors_rgba.get(z, "rgba(255,255,255,0.03)"),
                               line_width=0, row=2, col=1)

    apply_dark(fig_main)
    fig_main.update_layout(height=380, showlegend=True,
                            xaxis2_title="Time (minutes)")
    fig_main.update_yaxes(title_text="Watts", row=1, col=1)
    fig_main.update_yaxes(title_text="bpm", row=2, col=1)
    st.plotly_chart(fig_main, use_container_width=True)

    # ── 2. Speed + Altitude ───────────────────────────────────────────────────
    has_alt = any(a is not None for a in sd.altitude_ts)
    has_spd = any(s is not None for s in sd.speed_ts)

    if has_spd or has_alt:
        st.markdown('<div class="section-head">Speed & Elevation</div>', unsafe_allow_html=True)

        fig_sa = make_subplots(
            rows=2 if (has_spd and has_alt) else 1, cols=1,
            shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=(
                ("Speed (km/h)", "Altitude (m)") if has_spd and has_alt
                else ("Speed (km/h)",) if has_spd else ("Altitude (m)",)
            ),
        )
        row_spd = 1
        row_alt = 2 if has_spd else 1

        if has_spd:
            fig_sa.add_trace(go.Scatter(
                x=t_min, y=sd.speed_ts, mode="lines",
                name="Speed", line=dict(color="#5c85d6", width=1.2),
                fill="tozeroy", fillcolor="rgba(92,133,214,0.08)",
            ), row=row_spd, col=1)

        if has_alt:
            fig_sa.add_trace(go.Scatter(
                x=t_min, y=sd.altitude_ts, mode="lines",
                name="Altitude", line=dict(color="#4caf7d", width=1.5),
                fill="tozeroy", fillcolor="rgba(76,175,125,0.1)",
            ), row=row_alt, col=1)

        apply_dark(fig_sa)
        fig_sa.update_layout(height=280 if (has_spd and has_alt) else 180)
        st.plotly_chart(fig_sa, use_container_width=True)

    # ── 3. Zone distribution charts ───────────────────────────────────────────
    st.markdown('<div class="section-head">Zone Analysis</div>', unsafe_allow_html=True)
    zcol1, zcol2 = st.columns(2)

    with zcol1:
        # HR zones donut
        if ra.hr_zone_pct:
            z_labels = list(ra.hr_zone_pct.keys())
            z_pcts   = list(ra.hr_zone_pct.values())
            z_mins   = list(ra.hr_zone_min.values())
            z_cols   = [ZONE_COLORS.get(z, "#555") for z in z_labels]
            z_ranges = [f"{hr_zones[z][0]}–{hr_zones[z][1]} bpm" for z in z_labels]

            fig_hr_z = go.Figure(go.Pie(
                labels=[f"{z} ({r})" for z, r in zip(z_labels, z_ranges)],
                values=z_pcts,
                hole=0.55,
                marker_colors=z_cols,
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value:.1f}% · %{customdata:.0f} min<extra></extra>",
                customdata=z_mins,
            ))
            fig_hr_z.update_layout(
                title="HR Zone Distribution",
                annotations=[dict(text="HR<br>Zones", x=0.5, y=0.5,
                                  font_size=13, showarrow=False, font_color="#aaa")],
                **{k: v for k, v in PLOT_LAYOUT.items()},
                height=300, margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(fig_hr_z, use_container_width=True)

    with zcol2:
        # Power zones bar
        if ra.pwr_zone_pct:
            pz_labels = [f"Z{z}\n{POWER_ZONE_NAMES[z]}" for z in sorted(ra.pwr_zone_pct.keys())]
            pz_pcts   = [ra.pwr_zone_pct[z] for z in sorted(ra.pwr_zone_pct.keys())]
            pz_mins   = [ra.pwr_zone_min[z]  for z in sorted(ra.pwr_zone_min.keys())]
            pz_limits = power_zones_from_ftp(ftp)
            pz_ranges = [f"{int(pz_limits[z][0])}–{int(pz_limits[z][1])}W"
                         for z in sorted(pz_limits.keys())]
            bar_colors = ["#555", "#2979ff", "#4caf7d", "#f0b429", "#f06529", "#E8001D"]

            fig_pz = go.Figure(go.Bar(
                x=pz_labels, y=pz_pcts,
                marker_color=bar_colors[:len(pz_labels)],
                text=[f"{p:.0f}%" for p in pz_pcts],
                textposition="outside",
                hovertemplate="%{x}<br>%{y:.1f}%<br>%{customdata:.0f} min<extra></extra>",
                customdata=pz_mins,
            ))
            fig_pz.update_layout(
                title=f"Power Zone Distribution (FTP = {ftp}W)",
                yaxis_title="% time", showlegend=False,
                **{k: v for k, v in PLOT_LAYOUT.items()},
                height=300, margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(fig_pz, use_container_width=True)

    # ── 4. Cadence chart ─────────────────────────────────────────────────────
    if any(sd.cadence_ts):
        st.markdown('<div class="section-head">Cadence</div>', unsafe_allow_html=True)
        fig_cad = go.Figure()
        fig_cad.add_trace(go.Scatter(
            x=t_min, y=sd.cadence_ts, mode="lines",
            name="Cadence", line=dict(color="#888", width=1),
            fill="tozeroy", fillcolor="rgba(136,136,136,0.06)",
        ))
        fig_cad.add_hline(y=ra.avg_cadence, line=dict(color="#aaa", dash="dash", width=1),
                          annotation_text=f"Avg {ra.avg_cadence:.0f} rpm")
        apply_dark(fig_cad)
        fig_cad.update_layout(height=180, xaxis_title="Time (min)", yaxis_title="rpm")
        st.plotly_chart(fig_cad, use_container_width=True)

    # ── 5. Power Curve ────────────────────────────────────────────────────────
    st.markdown('<div class="section-head">Power Curve (Mean Maximal Power)</div>', unsafe_allow_html=True)

    if any(sd.power_ts):
        durations = [1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600]
        dur_labels = ["1s","5s","10s","30s","1m","2m","5m","10m","20m","30m","60m"]
        mmp_vals  = [ra.best_5s if d == 5 else
                     ra.best_30s if d == 30 else
                     ra.best_1min if d == 60 else
                     ra.best_5min if d == 300 else
                     ra.best_10min if d == 600 else
                     ra.best_20min if d == 1200 else
                     ra.best_60min if d == 3600 else
                     0
                     for d in durations]

        # Fill gaps with best_effort_watts for durations not pre-computed
        from fit_parser import best_effort_watts
        for i, d in enumerate(durations):
            if mmp_vals[i] == 0:
                mmp_vals[i] = best_effort_watts(sd.power_ts, d)

        mmp_wkg = [w / weight_kg for w in mmp_vals]

        fig_curve = make_subplots(specs=[[{"secondary_y": True}]])
        fig_curve.add_trace(go.Scatter(
            x=dur_labels, y=mmp_vals, mode="lines+markers",
            name="Watts", line=dict(color="#f0b429", width=2),
            marker=dict(size=7, color="#f0b429"),
        ), secondary_y=False)
        fig_curve.add_trace(go.Scatter(
            x=dur_labels, y=mmp_wkg, mode="lines+markers",
            name="W/kg", line=dict(color="#5c85d6", width=2, dash="dot"),
            marker=dict(size=6, color="#5c85d6"),
        ), secondary_y=True)

        # FTP line
        fig_curve.add_hline(y=ftp, line=dict(color="#E8001D", dash="dash", width=1),
                             annotation_text=f"FTP {ftp}W", secondary_y=False)

        apply_dark(fig_curve)
        fig_curve.update_layout(height=260, xaxis_title="Duration")
        fig_curve.update_yaxes(title_text="Watts", secondary_y=False)
        fig_curve.update_yaxes(title_text="W/kg", secondary_y=True, gridcolor="#1a1a1a")
        st.plotly_chart(fig_curve, use_container_width=True)

    # ── 6. Segment pacing table ────────────────────────────────────────────────
    st.markdown('<div class="section-head">15-Minute Segment Breakdown</div>', unsafe_allow_html=True)

    if ra.segments:
        seg_df = pd.DataFrame(ra.segments[:-1])  # exclude cooldown
        seg_df.columns = ["#", "Start (min)", "End (min)", "Avg Power (W)",
                           "Avg HR (bpm)", "Avg Speed (km/h)", "Avg Cadence (rpm)"]
        st.dataframe(
            seg_df.style
                .background_gradient(subset=["Avg Power (W)"], cmap="YlOrRd")
                .background_gradient(subset=["Avg HR (bpm)"],   cmap="RdYlGn_r")
                .format({"Avg Power (W)": "{:.0f}", "Avg HR (bpm)": "{:.0f}",
                         "Avg Speed (km/h)": "{:.1f}", "Avg Cadence (rpm)": "{:.0f}"}),
            use_container_width=True, height=None,
        )

    # ── 7. Laps ────────────────────────────────────────────────────────────────
    if sd.laps:
        st.markdown('<div class="section-head">Lap Summary</div>', unsafe_allow_html=True)
        lap_df = pd.DataFrame(sd.laps)
        lap_df.columns = ["Lap", "Duration (min)", "Distance (km)",
                           "Avg HR (bpm)", "Max HR (bpm)", "Avg Power (W)", "Avg Cadence (rpm)"]
        st.dataframe(lap_df, use_container_width=True)

    # ── 8. Key metrics summary row ─────────────────────────────────────────────
    st.markdown('<div class="section-head">Performance Metrics</div>', unsafe_allow_html=True)
    m1, m2, m3, m4, m5, m6 = st.columns(6)

    m1.metric("Normalized Power", f"{ra.np:.0f} W", f"{ra.np_wkg:.2f} W/kg")
    m2.metric("Variability Index", f"{ra.vi:.3f}",
              "Steady" if ra.vi < 1.05 else "Variable")
    m3.metric("Intensity Factor", f"{ra.if_val:.2f}",
              "Endurance" if ra.if_val < 0.75 else "Threshold" if ra.if_val < 0.85 else "Race")
    m4.metric("TSS", f"{ra.tss:.0f}",
              "Low" if ra.tss < 100 else "Medium" if ra.tss < 200 else "High")
    m5.metric("Cardiac Drift", f"{ra.cardiac_drift_pct:.1f}%",
              "✓ Good" if abs(ra.cardiac_drift_pct) < 5 else "⚠ High")
    m6.metric("Power Fade", f"{ra.power_fade_pct:.1f}%",
              "✓ Good" if ra.power_fade_pct > -8 else "⚠ Late fade")

    # ══════════════════════════════════════════════════════════════════════════
    # AI COACH
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-head">🤖 AI Coach Analysis</div>', unsafe_allow_html=True)

    if not api_key:
        st.info("👈 Add your Anthropic API key in the sidebar to unlock AI coaching analysis.")
    else:
        if st.button("Generate Coach Analysis", key="gen_coach"):
            with st.spinner("Your coach is reviewing the session…"):
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    prompt = build_coach_prompt(sd, ra)
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    coach_text = response.content[0].text
                    st.session_state["coach_analysis"] = coach_text
                except Exception as e:
                    st.error(f"AI error: {e}")

        if "coach_analysis" in st.session_state:
            st.markdown(
                f'<div class="coach-card">{st.session_state["coach_analysis"]}</div>',
                unsafe_allow_html=True
            )
            # Save to history button
            if st.button("💾 Save Session to Training Log"):
                save_session(sd, ra, uploaded.name,
                             coach_notes=st.session_state.get("coach_analysis", ""))
                st.success("Session saved to your training log! ✓")
        else:
            # Save without AI
            if st.button("💾 Save Session to Training Log (no AI analysis)"):
                save_session(sd, ra, uploaded.name)
                st.success("Session saved to your training log! ✓")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: TRAINING LOG / HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    history = load_history()

    if not history:
        st.markdown("### No sessions saved yet")
        st.markdown("Analyse a session and click **Save to Training Log** to start tracking your progress.")
        st.stop()

    st.markdown(f"### Training Log &nbsp;·&nbsp; <span style='color:#888;font-size:0.9rem;'>{len(history)} sessions</span>", unsafe_allow_html=True)

    # ── Trend charts ──────────────────────────────────────────────────────────
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date")

    if len(df) >= 2:
        st.markdown('<div class="section-head">Progress Trends</div>', unsafe_allow_html=True)

        tc1, tc2, tc3 = st.columns(3)

        with tc1:
            fig_pwr = go.Figure()
            fig_pwr.add_trace(go.Scatter(
                x=df["date"], y=df["np"], mode="lines+markers",
                name="NP", line=dict(color="#f0b429", width=2),
                marker=dict(size=6),
            ))
            fig_pwr.add_trace(go.Scatter(
                x=df["date"], y=df["best_20min_w"], mode="lines+markers",
                name="20min Best", line=dict(color="#f06529", width=1.5, dash="dot"),
                marker=dict(size=5),
            ))
            apply_dark(fig_pwr)
            fig_pwr.update_layout(title="Power Trend (W)", height=220,
                                   margin=dict(l=30, r=10, t=40, b=30))
            st.plotly_chart(fig_pwr, use_container_width=True)

        with tc2:
            fig_hr_t = go.Figure()
            fig_hr_t.add_trace(go.Scatter(
                x=df["date"], y=df["avg_hr"], mode="lines+markers",
                name="Avg HR", line=dict(color="#e8001d", width=2),
                marker=dict(size=6),
            ))
            apply_dark(fig_hr_t)
            fig_hr_t.update_layout(title="Avg HR Trend (bpm)", height=220,
                                    margin=dict(l=30, r=10, t=40, b=30))
            st.plotly_chart(fig_hr_t, use_container_width=True)

        with tc3:
            fig_tss = go.Figure()
            fig_tss.add_trace(go.Bar(
                x=df["date"], y=df["tss"],
                marker_color="#4caf7d", name="TSS",
            ))
            # Rolling 7-day CTL approximation
            if len(df) >= 7:
                tss_vals = df["tss"].fillna(0).tolist()
                ctl = []
                ctl_val = 0
                for t in tss_vals:
                    ctl_val = ctl_val * (1 - 1/42) + t * (1/42)
                    ctl.append(ctl_val)
                fig_tss.add_trace(go.Scatter(
                    x=df["date"], y=ctl, mode="lines",
                    name="CTL (fitness)", line=dict(color="#f0b429", width=2),
                ))
            apply_dark(fig_tss)
            fig_tss.update_layout(title="Training Load (TSS) & Fitness", height=220,
                                   margin=dict(l=30, r=10, t=40, b=30))
            st.plotly_chart(fig_tss, use_container_width=True)

    # ── W/kg trend ────────────────────────────────────────────────────────────
    if "best_20min_wkg" in df.columns and len(df) >= 2:
        st.markdown('<div class="section-head">W/kg Development (20-min Best)</div>', unsafe_allow_html=True)
        fig_wkg = go.Figure()
        fig_wkg.add_trace(go.Scatter(
            x=df["date"], y=df["best_20min_wkg"], mode="lines+markers",
            name="20min W/kg", line=dict(color="#5c85d6", width=2),
            marker=dict(size=8, color="#5c85d6"),
            fill="tozeroy", fillcolor="rgba(92,133,214,0.07)",
        ))
        # Target lines
        for target, label, color in [(3.0, "Cat 4 target", "#555"),
                                      (3.5, "Cat 3 target", "#888"),
                                      (4.0, "Cat 2 target", "#aaa")]:
            fig_wkg.add_hline(y=target, line=dict(color=color, dash="dot", width=1),
                              annotation_text=label)
        apply_dark(fig_wkg)
        fig_wkg.update_layout(height=220, yaxis_title="W/kg",
                               margin=dict(l=30, r=10, t=20, b=30))
        st.plotly_chart(fig_wkg, use_container_width=True)

    # ── Session table ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-head">All Sessions</div>', unsafe_allow_html=True)

    display_cols = ["date", "filename", "duration_min", "distance_km", "elevation_m",
                    "avg_power", "np", "best_20min_w", "avg_hr", "tss", "avg_cadence"]
    rename_map = {
        "date": "Date", "filename": "File", "duration_min": "Duration (min)",
        "distance_km": "Distance (km)", "elevation_m": "Elevation (m)",
        "avg_power": "Avg Power (W)", "np": "NP (W)",
        "best_20min_w": "Best 20min (W)", "avg_hr": "Avg HR",
        "tss": "TSS", "avg_cadence": "Avg Cadence",
    }

    disp_df = df[display_cols].rename(columns=rename_map).copy()
    disp_df["Date"] = disp_df["Date"].dt.strftime("%d %b %Y")

    st.dataframe(
        disp_df.style
            .background_gradient(subset=["NP (W)", "Best 20min (W)"], cmap="YlOrRd")
            .format({"Duration (min)": "{:.0f}", "Distance (km)": "{:.1f}",
                     "Avg Power (W)": "{:.0f}", "NP (W)": "{:.0f}",
                     "Best 20min (W)": "{:.0f}", "Avg HR": "{:.0f}",
                     "TSS": "{:.0f}", "Avg Cadence": "{:.0f}"}),
        use_container_width=True,
    )

    # ── Expandable coach notes ────────────────────────────────────────────────
    sessions_with_notes = [(i, h) for i, h in enumerate(history) if h.get("coach_notes")]
    if sessions_with_notes:
        st.markdown('<div class="section-head">Saved Coach Notes</div>', unsafe_allow_html=True)
        for i, h in sessions_with_notes[:5]:
            date_label = h.get("date", "Unknown")[:10]
            with st.expander(f"📝 {h.get('filename', 'Session')} — {date_label}"):
                st.markdown(h["coach_notes"])
                if st.button(f"🗑 Delete", key=f"del_{i}"):
                    delete_session(i)
                    st.rerun()

    # ── Delete all ────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("🗑 Clear All Sessions"):
        import json
        from pathlib import Path
        Path("training_history.json").write_text("[]")
        st.rerun()
