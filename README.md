# 🚴 Cycling Performance Analyser

A Streamlit web app that parses `.fit` files from any bike computer (Garmin, Wahoo, Zwift, etc.) and delivers a full performance analysis with AI coaching.

---

## Features

- **FIT file parsing** — no external libraries needed, pure Python parser
- **Power analysis** — NP, VI, IF, TSS, power curve (MMP), zone distribution
- **HR analysis** — custom HR zones, cardiac drift, zone time
- **Charts** — power + HR overview, speed/elevation, power curve, cadence, zone donuts
- **15-min segment breakdown** — pacing table with heat-map
- **AI Coach** — personalised analysis via Claude API (optional)
- **Training log** — saves sessions, tracks trends: power, HR, TSS, W/kg development

---

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

---

## Deploy to Streamlit Community Cloud (Free)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/cycling-analyser.git
   git push -u origin main
   ```

2. **Go to** [share.streamlit.io](https://share.streamlit.io)

3. **Click** "New app" → connect your GitHub repo

4. **Set:**
   - Repository: `YOUR_USERNAME/cycling-analyser`
   - Branch: `main`
   - Main file: `app.py`

5. **Click Deploy** — your app will be live at:
   `https://YOUR_USERNAME-cycling-analyser-app-XXXX.streamlit.app`

### Optional: Store API key securely on Streamlit Cloud
In your app settings on Streamlit Cloud, add a secret:
```toml
# .streamlit/secrets.toml (don't commit this file!)
ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## Project Structure

```
cycling_app/
├── app.py              # Main Streamlit application
├── fit_parser.py       # FIT binary file parser (no external deps)
├── analytics.py        # Metrics, zones, AI prompt builder
├── history.py          # Training log persistence (JSON)
├── requirements.txt    # Python dependencies
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---|---|
| streamlit | Web framework |
| plotly | Interactive charts |
| pandas | Data tables |
| numpy | Numerical ops |
| anthropic | Claude AI API (optional) |

---

## Rider Settings

Set in the sidebar:
- **Weight (kg)** — used for all W/kg calculations
- **FTP (W)** — used for power zones, IF, TSS
- **HR Zones** — fully customisable bpm ranges

---

## Training Log

Sessions are saved to `training_history.json` in the app directory.
On Streamlit Cloud, this resets on each deployment — to persist data across deployments,
you can mount a volume or integrate a simple database (e.g. Supabase, Firebase).

---

## AI Coach

Powered by Claude (Anthropic). Provide your API key in the sidebar.
Get a key at [console.anthropic.com](https://console.anthropic.com).
