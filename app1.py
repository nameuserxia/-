import os
import re
import json
from dotenv import load_dotenv
from amap import get_forbidden_zone 
load_dotenv()

import gradio as gr
from llm_gemini import parse_request

from planner import plan_3d_refine
from exporters import export_kml, export_gpx, export_mavlink, plot_route_on_map
# 在文件开头确保你 import 了 get_forbidden_zone
from amap import geocode, route_driving, get_area_polygon, get_forbidden_zone, AMAP_KEY

def handle_input(user_text):
    parsed = parse_request(user_text)
    print("Parsed request:", parsed)

    origin_val = parsed.get('origin')
    destination_val = parsed.get('destination')
    constraints = parsed.get('constraints', {}) or {}

    origin_str = origin_val if isinstance(origin_val, str) else origin_val.get('address', '')
    destination_str = destination_val if isinstance(destination_val, str) else destination_val.get('address', '')

    if not origin_str or not destination_str:
        return {"error": "Could not parse origin/destination.", "parsed": parsed}, None

    origin = geocode(origin_str)
    destination = geocode(destination_str)

    obstacles = []
    no_fly_zones = []

    # --- 解析多个 avoid 名称 ---
    if 'avoid' in constraints and constraints['avoid']:
        avoid_raw = constraints['avoid']
        if isinstance(avoid_raw, str):
            avoid_names = re.split(r'[，,、;；\s和]+', avoid_raw.strip())
            avoid_names = [n for n in avoid_names if n]
        elif isinstance(avoid_raw, (list,tuple)):
            avoid_names = list(avoid_raw)
        else:
            avoid_names = []

        for name in avoid_names:
            # 依据名称特征设定默认缓冲（可被 constraints 覆盖）
            # 更智能的办法是用 POI 类型判断 --- 这里使用简单启发式
            if any(k in name for k in ("机场","码头","港","河","高速","铁路")):
                default_buf = constraints.get('avoid_buffer_meters', 3000)
            elif any(k in name for k in ("公园","广场","学校","医院")):
                default_buf = constraints.get('avoid_buffer_meters', 800)
            elif len(name) <= 4:
                # 很短的名称，通常是小地名/街道
                default_buf = constraints.get('avoid_buffer_meters', 400)
            else:
                default_buf = constraints.get('avoid_buffer_meters', 1000)

            try:
                polys = get_forbidden_zone(name, key=AMAP_KEY, buffer_meters=default_buf)
                if polys:
                    obstacles.extend(polys)
                    print(f"Added {len(polys)} polygons for avoid area '{name}' with buffer {default_buf}m")
                else:
                    print(f"No polygons returned for area '{name}'")
            except Exception as e:
                print(f"Error fetching forbidden zone for '{name}': {e}")

    # explicit no_fly_zones (unchanged)
    # ...

    if not origin or not destination:
        return {"error": "Geocoding failed", "origin": origin, "destination": destination}, None

    route = route_driving(origin, destination)
    if not route or 'polyline_points' not in route:
        return {"error": "Amap routing failed"}, None

    combined_obstacles = []
    combined_obstacles.extend(obstacles)
    combined_obstacles.extend(no_fly_zones)

    # --- 自适应缓冲重试：尝试一系列缓冲值，直到规划器找到避障路径 ---
    # start with a conservative (较小) buffer set derived from constraints or defaults
    initial_buffer = constraints.get('avoid_buffer_meters', 1000)
    # 一系列尝试值（从大到小或从小到大都可以，这里从初始开始，然后递减）
    try_buffers = [initial_buffer, max(1000, initial_buffer//2), max(500, initial_buffer//4), 250, 100]

    refined = None
    used_buffer = None
        # ---------------- 在 handle_input 中，route 已拿到之后，替换掉原先 astar/refine 调用 ----------------
    # combined_obstacles 已合并 obstacles + no_fly_zones（每个是多边形 list）
    # 把它们规范为 polygon dict 或 list（planner 的函数支持 list-of-polys）
    polygons = []
    for p in combined_obstacles:
        # if dict zone with 'poly' key
        if isinstance(p, dict) and p.get('poly'):
            polygons.append(p['poly'])
        elif isinstance(p, list) and len(p) >= 3:
            polygons.append(p)
    # 解析 must_pass / stopover（支持字符串或列表）
    must_pass_pts = []
    if 'must_pass' in constraints and constraints['must_pass']:
        mp = constraints['must_pass']
        if isinstance(mp, str):
            names = re.split(r'[，,、;；\s和]+', mp.strip())
        elif isinstance(mp, (list,tuple)):
            names = list(mp)
        else:
            names = []
        for nm in names:
            g = geocode(nm)
            if g:
                must_pass_pts.append((g['lng'], g['lat']))
            else:
                print(f"[handle_input] could not geocode must_pass '{nm}'")

    stopover_pts = []
    if 'stopover' in constraints and constraints['stopover']:
        sp = constraints['stopover']
        if isinstance(sp, str):
            names = re.split(r'[，,、;；\s和]+', sp.strip())
        elif isinstance(sp, (list,tuple)):
            names = list(sp)
        else:
            names = []
        for nm in names:
            g = geocode(nm)
            if g:
                stopover_pts.append((g['lng'], g['lat']))
            else:
                print(f"[handle_input] could not geocode stopover '{nm}'")

    # build visit sequence: origin -> must_pass... -> stopover... -> destination
    seq = []
    seq.append((origin['lng'], origin['lat']))
    seq.extend(must_pass_pts)
    seq.extend(stopover_pts)
    seq.append((destination['lng'], destination['lat']))

    # buffer meters from constraints (horizontal buffer around obstacles when skirt)
    buf = constraints.get('avoid_buffer_meters', 500)  # 默认 500m，可按需改

    # call our simple planner: route_sequence_straight_skirt
    from planner import route_sequence_straight_skirt
    full2d = route_sequence_straight_skirt(seq, polygons, buffer_meters=buf)

    # attach altitude: use highlimit if provided, otherwise default flight altitude (e.g., 120m)
    try:
        highlimit = float(constraints.get('highlimit')) if constraints.get('highlimit') else None
    except Exception:
        highlimit = None
    flight_alt = 120.0 if highlimit is None else min(120.0, highlimit)

    refined = [(lng, lat, flight_alt) for (lng, lat) in full2d]

    # exports (unchanged)
    kml_path = export_kml(refined, 'route_kml.kml')
    gpx_path = export_gpx(refined, 'route_gpx.gpx')
    mav_path = export_mavlink(refined, 'route_mavlink.mavlink')


    result_json = {
        "origin": origin,
        "destination": destination,
        "constraints": constraints,
        "amap_route_summary": {"points": len(route['polyline_points'])},
        "refined_waypoints_count": len(refined),
        "refined_waypoints": refined,
        "kml": kml_path,
        "gpx": gpx_path,
        "mavlink": mav_path,
        "used_avoid_buffer_meters": used_buffer,
        "obstacles_count": len(combined_obstacles)
    }

    # 可视化（和你原始代码一致）
    original_pts = route['polyline_points']
    refined_2d = [(lng, lat) for (lng, lat, *rest) in refined]
    route_map = plot_route_on_map(
        original_points=original_pts,
        refined_points=refined_2d,
        origin=origin,
        destination=destination,
        no_fly_polygons=combined_obstacles
    )

    return result_json, route_map



with gr.Blocks() as demo:
    gr.Markdown("""
# AI Drone Route Agent (Amap + Gemini)

Enter natural language route requests, for example:  
"Plan a drone route from 中北大学 to 太原理工 avoiding the airport and a restricted polygon"
""")
    inp = gr.Textbox(lines=3, placeholder="Enter request...")
    out_json = gr.JSON(label="Route Data")
    out_map = gr.HTML(label="Route Visualization")
    btn = gr.Button("Plan Route")
    btn.click(fn=handle_input, inputs=inp, outputs=[out_json, out_map])

    if __name__ == '__main__':
        demo.launch()
