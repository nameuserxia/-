# AI Agent for Route Planning with Amap + Google Gemini + Gradio

This repository is a ready-to-run prototype that implements an AI agent which:
- Accepts natural language route requests.
- Uses Google Gemini (via `google-generativeai`) to parse intent and parameters.
- Calls Amap (高德) Web API to fetch POI/geocoding/route info.
- Performs simple path planning (A*; RRT* stub included).
- Visualizes route in a Gradio interface and embedded Three.js viewer.
- Exports KML/GPX/MAVLink.
- Provides hooks for PX4/SITL via MAVLink.

## Features (MVP)
- Natural language input -> LLM (Gemini) parses origin, destination, constraints.
- Amap API integration for geocoding and route guidance.
- A* planner that can refine Amap polyline into waypoint graph planning.（It didn't work well after actual testing, so I've given up）
- Gradio UI with map preview, 3D visualization using Three.js, and export options.

## Requirements
- Python 3.10+
- See `requirements.txt` for Python dependencies.

## Setup
1. Clone or extract this repo.
2. Create virtualenv and install requirements:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Create `.env` file (or copy `.env.sample`) and fill in your API keys:
   ```env
   GEMINI_API_KEY=your_gemini_api_key
   AMAP_API_KEY=your_amap_key
   ```
4. Run the app:
   ```bash
   python app.py
   ```
5. Open the Gradio URL printed in console and try:
   ```
   Plan a drone route from The Bund, Shanghai to Pudong Airport avoiding restricted zones.
   ```

## Notes
- Keep your API keys secret.
- This is a prototype — add production-grade error handling, rate limit handling, caching, authentication, and compliance with Amap & Google usage terms before production use.
