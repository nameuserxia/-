# amap.py -- compatible, complete version
import os
import math
import requests
from dotenv import load_dotenv
load_dotenv()

# API key (try common env names)
AMAP_KEY = os.getenv('AMAP_API_KEY') or os.getenv('AMAP_KEY') or ''

BASE = 'https://restapi.amap.com/v3'
BASE_V5 = 'https://restapi.amap.com/v5'

# ---------------- geocode ----------------
def get_poi_detail_by_id(poi_id, key=AMAP_KEY):
    """
    Try v3 place/detail to fetch more fields for a POI id.
    Returns dict or None.
    """
    url = BASE + "/place/detail"
    params = {"key": key, "id": poi_id, "output": "JSON"}
    try:
        r = requests.get(url, params=params, timeout=8)
        j = r.json()
    except Exception as e:
        print(f"[get_poi_detail_by_id] request error: {e}")
        return None
    if isinstance(j, dict) and j.get("status") == "1" and j.get("poi"):
        return j["poi"]
    return None


def geocode(address, key=AMAP_KEY):
    """Return {'address':address, 'lng':float, 'lat':float} or None"""
    if not key:
        print("[amap] Warning: AMAP_KEY empty")
    url = BASE + '/geocode/geo'
    params = {'key': key, 'address': address}
    try:
        r = requests.get(url, params=params, timeout=10)
        j = r.json()
    except Exception as e:
        print(f"[amap.geocode] request error: {e}")
        return None
    if j.get('status') != '1' or not j.get('geocodes'):
        return None
    g = j['geocodes'][0]
    try:
        lng, lat = map(float, g['location'].split(','))
    except Exception:
        return None
    return {'address': address, 'lng': lng, 'lat': lat}

# ---------------- district polygon ----------------
def get_area_polygon(area_name, key=AMAP_KEY, subdistrict=3, retry=2):
    """
    Get administrative polygons for area_name (recursive).
    Returns list of polygons, each polygon is [(lon,lat),...]
    """
    url = BASE + "/config/district"
    params = {
        'keywords': area_name,
        'subdistrict': subdistrict,
        'extensions': 'all',
        'output': 'json',
        'key': key
    }
    for _ in range(retry):
        try:
            r = requests.get(url, params=params, timeout=8)
            j = r.json()
        except Exception as e:
            print(f"[amap.get_area_polygon] request error: {e}")
            continue
        if j.get('status') != '1' or not j.get('districts'):
            # no matching district
            return []
        district = j['districts'][0]
        polyline_str = district.get('polyline', '') or district.get('boundary', '')
        polygons = []
        if polyline_str:
            for ring in polyline_str.split('|'):
                pts = []
                for pair in ring.split(';'):
                    if not pair:
                        continue
                    try:
                        lon, lat = pair.split(',')
                        pts.append((float(lon), float(lat)))
                    except Exception:
                        continue
                if len(pts) >= 3:
                    polygons.append(pts)
        if polygons:
            return polygons
        # if no polyline, try sub-districts
        if 'districts' in district and district['districts']:
            subs = district['districts']
            collected = []
            for s in subs:
                name = s.get('name')
                if not name:
                    continue
                res = get_area_polygon(name, key=key, subdistrict=1, retry=1)
                if res:
                    collected.extend(res)
            if collected:
                return collected
    # failed
    return []

# ---------------- place/text (POI) and road polyline ----------------
def parse_polyline_str(polyline_str):
    pts = []
    if not polyline_str:
        return pts
    for seg in polyline_str.split(';'):
        seg = seg.strip()
        if not seg:
            continue
        try:
            lon, lat = seg.split(',')
            pts.append((float(lon), float(lat)))
        except Exception:
            continue
    return pts

def get_road_polyline(road_name, key=AMAP_KEY, city=None):
    """Try to find a road polyline via place/text POI search. Returns list of (lon,lat) or []"""
    url = BASE + "/place/text"
    params = {"key": key, "keywords": road_name, "offset": 20, "page":1, "extensions":"all"}
    if city:
        params["city"] = city
    try:
        r = requests.get(url, params=params, timeout=8)
        j = r.json()
    except Exception as e:
        print(f"[amap.get_road_polyline] request error: {e}")
        return []
    pois = j.get("pois", []) if isinstance(j, dict) else []
    # try to find first poi with polyline
    for poi in pois:
        poly = poi.get("polyline") or poi.get("biz_ext", {}).get("polyline", "")
        if poly:
            pts = parse_polyline_str(poly)
            if pts:
                return pts
    # fallback: use first poi location as a single point
    if pois:
        loc = pois[0].get("location")
        if loc:
            try:
                lon, lat = map(float, loc.split(","))
                return [(lon, lat)]
            except:
                pass
    return []

# ---------------- buffering helpers ----------------
def circle_buffer(center, buffer_m, n=24):
    lon0, lat0 = center
    lat0_rad = math.radians(lat0)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111320.0 * math.cos(lat0_rad)
    r_lon = buffer_m / m_per_deg_lon
    r_lat = buffer_m / m_per_deg_lat
    poly = []
    for i in range(n):
        ang = 2*math.pi * i / n
        dx = math.cos(ang)
        dy = math.sin(ang)
        poly.append((lon0 + dx * r_lon, lat0 + dy * r_lat))
    if poly[0] != poly[-1]:
        poly.append(poly[0])
    return poly

def polyline_to_buffered_polygon(polyline, buffer_m):
    if not polyline:
        return []
    if len(polyline) == 1:
        return circle_buffer(polyline[0], buffer_m, n=24)
    mean_lat = sum(p[1] for p in polyline) / len(polyline)
    mean_lat_rad = math.radians(mean_lat)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111320.0 * math.cos(mean_lat_rad)
    XY = [((lon * m_per_deg_lon), (lat * m_per_deg_lat)) for lon,lat in polyline]
    normals = []
    for i in range(len(XY)):
        if i == 0:
            x0,y0 = XY[0]; x1,y1 = XY[1]
            vx, vy = x1-x0, y1-y0
        elif i == len(XY)-1:
            x0,y0 = XY[-2]; x1,y1 = XY[-1]
            vx, vy = x1-x0, y1-y0
        else:
            xa,ya = XY[i-1]; xb,yb = XY[i]; xc,yc = XY[i+1]
            vx1,vy1 = xb-xa, yb-ya
            vx2,vy2 = xc-xb, yc-yb
            vx,vy = (vx1+vx2)*0.5, (vy1+vy2)*0.5
        norm = math.hypot(vx,vy)
        if norm == 0:
            nx,ny = 0.0, 0.0
        else:
            nx,ny = -vy/norm, vx/norm
        normals.append((nx,ny))
    left_pts = []
    right_pts = []
    for (x,y), (nx,ny) in zip(XY, normals):
        lx, ly = x + nx*buffer_m, y + ny*buffer_m
        rx, ry = x - nx*buffer_m, y - ny*buffer_m
        left_pts.append((lx,ly))
        right_pts.append((rx,ry))
    poly_m = left_pts + right_pts[::-1]
    poly_lonlat = []
    for xm, ym in poly_m:
        lon = xm / m_per_deg_lon
        lat = ym / m_per_deg_lat
        poly_lonlat.append((lon, lat))
    if poly_lonlat[0] != poly_lonlat[-1]:
        poly_lonlat.append(poly_lonlat[0])
    return poly_lonlat

# ---------------- unified forbidden-zone getter ----------------
def get_forbidden_zone(name, key=AMAP_KEY, buffer_meters=500):
    """
    根据地名/POI名称获取避飞区多边形。
    优先级：
      1) 行政区 polygon (config/district)
      2) place/text -> poi.polyline / place/detail extra fields
      3) POI location -> circle_buffer
      4) geocode fallback -> circle_buffer
    返回 list of polygons (each polygon = list of (lng,lat))
    """
    print(f"[get_forbidden_zone] Resolve '{name}' with buffer {buffer_meters}m")

    # 1) 尝试行政区 polygon（与你原来的 get_area_polygon 保持兼容）
    polys = get_area_polygon(name, key=key)
    if polys:
        print(f"[get_forbidden_zone] Found {len(polys)} polygons via district for '{name}'")
        return polys

    # 2) place/text 搜索 POI（尝试 polyline/biz_ext 等）
    url = BASE + "/place/text"
    params = {"key": key, "keywords": name, "extensions": "all", "offset": 10}
    try:
        r = requests.get(url, params=params, timeout=8)
        j = r.json()
    except Exception as e:
        print(f"[get_forbidden_zone] place/text request error: {e}")
        j = {}
    pois = j.get("pois", []) if isinstance(j, dict) else []
    print(f"[get_forbidden_zone] place/text returned {len(pois)} pois for '{name}'")

    for idx, poi in enumerate(pois):
        # 1) 优先 polyline 字段（部分 POI/道路会有）
        polyline = poi.get("polyline") or (poi.get("biz_ext") or {}).get("polyline")
        if polyline:
            parsed = parse_polyline_str(polyline)
            if parsed:
                print(f"[get_forbidden_zone] Using POI polyline (poi #{idx}) for '{name}'")
                return [parsed]
        # 2) 如果 place/text 没有 polyline，尝试 place/detail 拿更详尽数据
        poi_id = poi.get("id")
        if poi_id:
            detail = get_poi_detail_by_id(poi_id, key=key)
            if detail:
                # 尝试多个可能存边界的字段
                for fld in ("polyline", "boundary", "shape", "polygon"):
                    val = detail.get(fld) or (detail.get("biz_ext") or {}).get(fld)
                    if val:
                        candidate = parse_polyline_str(val) if isinstance(val, str) else None
                        if candidate:
                            print(f"[get_forbidden_zone] Using place/detail {fld} for poi id {poi_id}")
                            return [candidate]
        # 3) fallback: 使用 location（中心点）生成缓冲多边形
        loc = poi.get("location")
        if loc:
            try:
                lon, lat = map(float, loc.split(","))
                print(f"[get_forbidden_zone] Using POI location buffer (poi #{idx}) for '{name}' at {lon},{lat}")
                return [circle_buffer((lon, lat), buffer_meters)]
            except Exception:
                pass

    # 3) 最后尝试 geocode
    g = geocode(name, key=key)
    if g:
        print(f"[get_forbidden_zone] Using geocode fallback for '{name}' at ({g['lng']},{g['lat']})")
        return [circle_buffer((g["lng"], g["lat"]), buffer_meters)]

    print(f"[get_forbidden_zone] Failed to resolve: {name}")
    return []

# ---------------- driving route ----------------
def route_driving(origin, destination, key=AMAP_KEY):
    """
    origin/destination: {'lng':..., 'lat':...}
    Returns {'raw': raw_api_json, 'polyline_points': [(lng,lat), ...]} or None
    """
    if not origin or not destination:
        return None
    url = BASE + '/direction/driving'
    origin_str = f"{origin['lng']},{origin['lat']}"
    dest_str = f"{destination['lng']},{destination['lat']}"
    params = {'key': key, 'origin': origin_str, 'destination': dest_str}
    try:
        r = requests.get(url, params=params, timeout=10)
        j = r.json()
    except Exception as e:
        print(f"[amap.route_driving] request error: {e}")
        return None
    if j.get('status') != '1' or not j.get('route'):
        return None
    try:
        path = j['route']['paths'][0]
        steps = path.get('steps', [])
        polyline = []
        for s in steps:
            ps = s.get('polyline','')
            for seg in ps.split(';'):
                if not seg:
                    continue
                try:
                    lon, lat = map(float, seg.split(','))
                    polyline.append((lon, lat))
                except:
                    continue
        return {'raw': j, 'polyline_points': polyline}
    except Exception as e:
        print(f"[amap.route_driving] parse error: {e}")
        return None

# ---------------- compatibility exports ----------------
# ensure the old import names used by app1.py are available
# geocode is already defined above (named geocode)
__all__ = [
    "geocode",
    "route_driving",
    "get_area_polygon",
    "get_forbidden_zone",
    "AMAP_KEY",
]


