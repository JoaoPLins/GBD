import json
import csv
import math
from pathlib import Path

def point_to_line_distance(point, line_start, line_end):
    """Calculate distance from point to line segment."""
    px, py = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # Vector from line_start to line_end
    dx = x2 - x1
    dy = y2 - y1
    
    # If line segment has zero length, return distance to endpoint
    if dx == 0 and dy == 0:
        return math.sqrt((px - x1)**2 + (py - y1)**2)
    
    # Parameter t represents position along line segment
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx**2 + dy**2)))
    
    # Closest point on line segment
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    # Distance to closest point
    return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)

def edges_share_segment(edge1, edge2, threshold=1e-6):
    """
    Check if two edges share a common segment (collinear and overlapping).
    Returns True if edges are on the same line and overlap for a meaningful distance.
    """
    (x1, y1), (x2, y2) = edge1
    (x3, y3), (x4, y4) = edge2
    
    # Check if all four points are collinear
    def cross_product(o, a, b):
        """Calculate cross product of vectors OA and OB."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    
    def are_collinear(p1, p2, p3, p4, epsilon=1e-6):
        """Check if all 4 points lie on the same line."""
        return (abs(cross_product(p1, p2, p3)) < epsilon and 
                abs(cross_product(p1, p2, p4)) < epsilon)
    
    if not are_collinear((x1, y1), (x2, y2), (x3, y3), (x4, y4)):
        return False
    
    # Points are collinear, now check if segments overlap
    # Project onto axis with larger extent
    dx1 = x2 - x1
    dy1 = y2 - y1
    
    if abs(dx1) > abs(dy1):
        # Project onto x-axis
        min_e1, max_e1 = min(x1, x2), max(x1, x2)
        min_e2, max_e2 = min(x3, x4), max(x3, x4)
    else:
        # Project onto y-axis
        min_e1, max_e1 = min(y1, y2), max(y1, y2)
        min_e2, max_e2 = min(y3, y4), max(y3, y4)
    
    # Check for overlap: segments share more than just a point
    overlap_start = max(min_e1, min_e2)
    overlap_end = min(max_e1, max_e2)
    
    # Return True only if there's meaningful overlap (not just a point)
    return overlap_end > overlap_start + 1e-6

def polygons_touching(poly1_coords, poly2_coords, threshold=10):
    """
    Check if two polygons share actual edge segments (not just touching at vertices).
    """
    def get_all_edges(coords):
        """Extract all line segments (edges) from MultiPolygon coordinates."""
        edges = []
        for polygon in coords:
            for ring in polygon:
                for i in range(len(ring) - 1):
                    edges.append((ring[i], ring[i+1]))
        return edges
    
    edges1 = get_all_edges(poly1_coords)
    edges2 = get_all_edges(poly2_coords)
    
    # Check if any edges share a segment
    for edge1 in edges1:
        for edge2 in edges2:
            if edges_share_segment(edge1, edge2):
                return True
    
    return False

def find_nearby_provinces(geojson_file, output_csv, border_threshold=10):
    """
    Find provinces that are touching or nearly touching at their borders.
    Output: CSV with province_id, nearby_provinces
    """
    with open(geojson_file, 'r') as f:
        data = json.load(f)
    
    # Store province geometries
    provinces = {}
    for feature in data['features']:
        prov_id = feature['properties']['id']
        prov_name = feature['properties'].get('p_name', f'Province_{prov_id}')
        geometry = feature['geometry']
        
        if geometry['type'] == 'MultiPolygon':
            # Store coordinates directly
            provinces[prov_id] = {
                'name': prov_name,
                'coordinates': geometry['coordinates']
            }
        elif geometry['type'] == 'Polygon':
            # Convert single polygon to multipolygon format
            provinces[prov_id] = {
                'name': prov_name,
                'coordinates': [geometry['coordinates']]
            }
    
    # Find nearby provinces for each province
    nearby_map = {}
    for prov_id, prov_data in provinces.items():
        nearby = []
        for other_id, other_data in provinces.items():
            if prov_id != other_id:
                # Check if polygons are touching or nearly touching
                if polygons_touching(prov_data['coordinates'], other_data['coordinates'], border_threshold):
                    nearby.append(other_id)
        
        nearby_map[prov_id] = nearby
    
    # Write to CSV
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['province_id', 'province_name', 'nearby_provinces'])
        
        for prov_id in sorted(provinces.keys()):
            prov_name = provinces[prov_id]['name']
            nearby_list = nearby_map.get(prov_id, [])
            nearby_ids = ','.join([str(other_id) for other_id in nearby_list]) if nearby_list else ''
            writer.writerow([prov_id, prov_name, nearby_ids])
    
    print(f"Nearby provinces CSV written to: {output_csv}")
    print(f"Border proximity threshold: {border_threshold} units")
    print(f"Total provinces: {len(provinces)}")

def create_prv_sheets(json_file, output_file):
    pass

if __name__ == '__main__':
    # Get the directory of this script
    script_dir = Path(__file__).parent
    
    # Input and output file paths
    geojson_path = script_dir / 'provinces.geojson'
    output_path = script_dir / 'nearby_provinces.csv'
    
    # Border proximity threshold in coordinate units
    # Lower values = only directly touching provinces
    # Higher values = provinces that are close but not touching
    find_nearby_provinces(str(geojson_path), str(output_path), border_threshold=5)