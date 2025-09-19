import simplekml, gpxpy, gpxpy.gpx, os
import folium

def export_kml(waypoints, filename='route.kml'):
    """
    waypoints: list of (lng, lat) or (lng, lat, alt)
    """
    kml = simplekml.Kml()
    for i,wp in enumerate(waypoints):
        lng = wp[0]; lat = wp[1]
        if len(wp) >= 3:
            alt = float(wp[2])
            kml.newpoint(name=f'wp{i}', coords=[(lng,lat,alt)])
        else:
            kml.newpoint(name=f'wp{i}', coords=[(lng,lat)])
    kml.save(filename)
    return os.path.abspath(filename)

def export_gpx(waypoints, filename='route.gpx'):
    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    seg = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(seg)
    for wp in waypoints:
        lng, lat = wp[0], wp[1]
        if len(wp) >= 3:
            ele = float(wp[2])
            seg.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lng, elevation=ele))
        else:
            seg.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lng))
    with open(filename,'w') as f:
        f.write(gpx.to_xml())
    return os.path.abspath(filename)

def export_mavlink(waypoints, filename='route.mavlink'):
    """
    Very simple MAVLink mission stub: CSV lines with index,lat,lon,alt
    """
    with open(filename,'w') as f:
        f.write('# MAVLink mission stub\n')
        for i,wp in enumerate(waypoints):
            lng, lat = wp[0], wp[1]
            alt = wp[2] if len(wp) >= 3 else 0
            f.write(f'{i},{lat},{lng},{alt}\n')
    return os.path.abspath(filename)


def plot_route_on_map(original_points, refined_points, origin, destination, no_fly_polygons=None):
    m = folium.Map(location=[origin['lat'], origin['lng']], zoom_start=7)
    folium.Marker([origin['lat'], origin['lng']], popup="Origin").add_to(m)
    folium.Marker([destination['lat'], destination['lng']], popup="Destination").add_to(m)

    if original_points:
        formatted_original_points = [[lat, lng] for lng, lat in original_points]
        folium.PolyLine(locations=formatted_original_points, weight=4, popup="Original").add_to(m)
    if refined_points:
        formatted_refined_points = [[lat, lng] for lng, lat in refined_points]
        folium.PolyLine(locations=formatted_refined_points, weight=4, popup="Refined", color='red').add_to(m)

    # draw no-fly polygons
    if no_fly_polygons:
        for poly in no_fly_polygons:
            folium.Polygon(locations=[[lat, lng] for lng, lat in poly],
                           color='crimson', fill=True, fill_opacity=0.25,
                           popup='No-Fly Zone').add_to(m)
    m.fit_bounds([[origin['lat'], origin['lng']], [destination['lat'], destination['lng']]])
    return m._repr_html_()

