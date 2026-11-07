#!/usr/bin/env python3
"""
Room Spatial Tool - Compute absolute positions from wall-relative YAML.

Usage:
  python room_spatial.py <room.yaml>                         # All positions
  python room_spatial.py <room.yaml> --view x,y              # View from point to edges
  python room_spatial.py <room.yaml> --gap item1 item2       # Edge-to-edge distance
  python room_spatial.py <room.yaml> --matrix                # All edge-to-edge distances
  python room_spatial.py <room.yaml> --plot [output.png]     # Floor plan image
  python room_spatial.py <room.yaml> --check                 # Run clearance rules engine
  python room_spatial.py <room.yaml> --json                  # Machine-readable output

--view:   distance from a POINT to object edges (use for viewpoints)
--gap:    distance EDGE-TO-EDGE between two items (use for furniture gaps)
--matrix: all pairwise edge-to-edge distances (furniture/built-ins only)
--check:  evaluate rules from scripts/rules/clearances.yaml (CIRC, SEAT, DIN,
          BED, TV, KIT, DOOR, WIN, HEAT, LIGHT, PROP, RUG + zones/sightlines).
          Findings: "SEVERITY RULE-ID: detail" (ERROR/WARN/SKIP). Exit code 1
          if any ERROR (geometry warnings count as ERROR under --check).
--json:   dump corners, objects, validation warnings (+ rule findings with
          --check) as JSON instead of text.
"""

import yaml
import sys
import math
import json
import heapq
import argparse
from pathlib import Path

# When emitting JSON we must not pollute stdout with inline warnings.
_JSON_MODE = False

def note(msg, **kwargs):
    """Print an inline note/warning - to stderr in JSON mode to keep stdout clean."""
    if _JSON_MODE:
        print(msg, file=sys.stderr, **kwargs)
    else:
        print(msg, **kwargs)

DIRECTIONS = {
    'north': (0, 1),
    'south': (0, -1),
    'east': (1, 0),
    'west': (-1, 0),
}

def trace_corners(walls):
    """Trace walls to compute corner coordinates. Origin at first corner."""
    # Get first corner name from first wall
    first_wall = walls[0]['id']
    first_corner = first_wall.split('-')[0]
    
    corners = {first_corner: (0, 0)}
    pos = [0, 0]
    
    for wall in walls:
        wall_id = wall['id']
        start, end = wall_id.split('-')
        dx, dy = DIRECTIONS[wall['direction']]
        length = wall['length']
        
        pos[0] += dx * length
        pos[1] += dy * length
        
        # Don't overwrite origin
        if end != first_corner:
            corners[end] = tuple(pos)
    
    # Check closure
    closure_gap = math.sqrt(pos[0]**2 + pos[1]**2)
    if closure_gap > 1:
        note(f"# WARNING: Trace doesn't close! Gap: {closure_gap:.0f}cm")
    
    return corners

def resolve_position(pos, corners, item_id=None):
    """Convert wall-relative position to absolute (x, y).
    
    Position is defined by two PERPENDICULAR reference walls and offsets.
    - offset[0] = perpendicular distance from wall[0] INTO the room
    - offset[1] = perpendicular distance from wall[1] INTO the room
    
    Walls trace clockwise around room, so "into room" = left of wall direction.
    Walls MUST be perpendicular - parallel walls cannot define a unique position.
    """
    if isinstance(pos, dict):
        if 'wall' in pos and 'offset' in pos:
            walls = pos['wall']
            offsets = pos['offset']
            
            # Wall 1
            w1_start, w1_end = walls[0].split('-')
            w1_s = corners[w1_start]
            w1_e = corners[w1_end]
            w1_vec = (w1_e[0] - w1_s[0], w1_e[1] - w1_s[1])
            w1_len = math.sqrt(w1_vec[0]**2 + w1_vec[1]**2)
            # Perpendicular into room = rotate 90° counterclockwise
            w1_perp = (-w1_vec[1]/w1_len, w1_vec[0]/w1_len)
            
            # Wall 2
            w2_start, w2_end = walls[1].split('-')
            w2_s = corners[w2_start]
            w2_e = corners[w2_end]
            w2_vec = (w2_e[0] - w2_s[0], w2_e[1] - w2_s[1])
            w2_len = math.sqrt(w2_vec[0]**2 + w2_vec[1]**2)
            w2_perp = (-w2_vec[1]/w2_len, w2_vec[0]/w2_len)
            
            # Check if walls are perpendicular (dot product ≈ 0)
            dot = (w1_vec[0] * w2_vec[0] + w1_vec[1] * w2_vec[1]) / (w1_len * w2_len)
            
            if abs(dot) > 0.1:
                # Walls are parallel - INVALID per spec
                name = item_id or "unknown"
                note(f"# WARNING: {name} uses parallel walls {walls} - position undefined!")
                return None
            
            # Walls are perpendicular - use intersection of offset lines
            # Wall1 is vertical (N-S) → sets x; Wall1 is horizontal (E-W) → sets y
            x, y = 0, 0
            
            if abs(w1_vec[0]) < 0.1:  # Wall1 vertical, sets x
                x = w1_s[0] + w1_perp[0] * offsets[0]
            else:  # Wall1 horizontal, sets y
                y = w1_s[1] + w1_perp[1] * offsets[0]
            
            if abs(w2_vec[0]) < 0.1:  # Wall2 vertical, sets x
                x = w2_s[0] + w2_perp[0] * offsets[1]
            else:  # Wall2 horizontal, sets y
                y = w2_s[1] + w2_perp[1] * offsets[1]
            
            return (round(x), round(y))
    
    return None

def load_room(path):
    """Load and parse room YAML."""
    with open(path) as f:
        return yaml.safe_load(f)

def load_registry(room_path, registry_path):
    """Load registry YAML relative to room file's project root."""
    if not registry_path:
        return None
    # Find project root (parent of 'rooms' directory)
    room_file = Path(room_path)
    project_root = room_file.parent.parent
    full_path = project_root / registry_path
    if full_path.exists():
        with open(full_path) as f:
            return yaml.safe_load(f)
    return None

# Controlled vocabulary for item types (explicit `type:` field on furniture/built-ins)
ITEM_TYPES = (
    'sofa', 'armchair', 'coffee-table', 'side-table', 'dining-table',
    'dining-chair', 'desk', 'desk-chair', 'bed', 'nightstand', 'wardrobe',
    'dresser', 'bookshelf', 'tv', 'rug', 'floor-lamp', 'table-lamp',
    'pendant', 'plant', 'kitchen', 'island', 'other',
)

# Keyword sniffing fallback (extends the DIRECTIONAL_KEYWORDS approach).
# Order matters: more specific keywords first.
TYPE_KEYWORDS = [
    ('rug', ('rug', 'carpet')),         # before 'dining' so dining-rug stays a rug
    ('coffee-table', ('coffee',)),
    ('side-table', ('side-table', 'end-table', 'sidetable')),
    ('nightstand', ('nightstand', 'bedside-table', 'night-table')),
    ('dining-chair', ('dining-chair',)),
    ('dining-table', ('dining-table', 'dining',)),
    ('desk-chair', ('desk-chair', 'office-chair', 'task-chair')),
    ('desk', ('desk',)),
    ('armchair', ('armchair', 'accent-chair', 'lounge-chair')),
    ('dining-chair', ('chair',)),       # plain "chair" defaults to dining
    ('sofa', ('sofa', 'couch', 'settee', 'loveseat')),
    ('wardrobe', ('wardrobe', 'closet', 'armoire')),
    ('dresser', ('dresser', 'chest-of-drawers', 'drawers', 'commode')),
    ('bookshelf', ('bookshelf', 'bookcase', 'shelving', 'shelf', 'shelves')),
    ('tv', ('tv', 'television')),
    ('floor-lamp', ('floor-lamp', 'floorlamp')),
    ('table-lamp', ('table-lamp', 'tablelamp', 'lamp')),
    ('pendant', ('pendant', 'chandelier')),
    ('plant', ('plant', 'tree', 'monstera', 'ficus')),
    ('island', ('island',)),
    ('kitchen', ('kitchen', 'counter', 'cabinets', 'hob', 'stove')),
    ('bed', ('bed', 'mattress')),
]

def sniff_type(obj_id):
    """Infer item type from id keywords. Returns 'other' if nothing matches."""
    lowered = obj_id.lower()
    for item_type, keywords in TYPE_KEYWORDS:
        for kw in keywords:
            if kw in lowered:
                return item_type
    return 'other'

def detect_item_type(item, obj_id):
    """Detect furniture/built-in type: explicit type: field, else id keywords."""
    declared = item.get('type')
    if declared:
        declared = str(declared).lower()
        if declared in ITEM_TYPES:
            return declared
        note(f"# WARNING: {obj_id} has unknown type '{declared}' - falling back to id keywords", )
    return sniff_type(obj_id)

def vec_to_axis(vec):
    """Convert unit vector to axis label (N-S or E-W)."""
    if abs(vec[1]) > abs(vec[0]):
        return 'N-S'  # primarily vertical
    else:
        return 'E-W'  # primarily horizontal

def vec_to_cardinal(vec):
    """Convert unit vector to cardinal direction (north/south/east/west)."""
    if abs(vec[1]) > abs(vec[0]):
        return 'north' if vec[1] > 0 else 'south'
    else:
        return 'east' if vec[0] > 0 else 'west'

def get_wall_directions(walls_ref, corners):
    """Get unit vectors for wall pair. Returns (along, perp, width_axis, facing)."""
    w1_start, w1_end = walls_ref[0].split('-')
    w1_vec = (
        corners[w1_end][0] - corners[w1_start][0],
        corners[w1_end][1] - corners[w1_start][1]
    )
    w1_len = math.sqrt(w1_vec[0]**2 + w1_vec[1]**2)
    along = (w1_vec[0]/w1_len, w1_vec[1]/w1_len)
    
    # Perpendicular (rotate 90° counterclockwise for "into room")
    perp = (-along[1], along[0])
    
    # Width axis = direction the first dimension (width) runs along
    width_axis = vec_to_axis(along)
    # Facing = direction the front points (perpendicular into room)
    facing = vec_to_cardinal(perp)
    
    return along, perp, width_axis, facing

def compute_bbox(pos, dims, along, perp):
    """Compute bounding box corners from position, dimensions, and directions.
    
    Position is the corner of object nearest to reference walls.
    Object extends in 'along' direction by width, in 'perp' direction by depth.
    """
    if not dims:
        return None
    
    width = dims.get('width', dims.get('length', 100))
    depth = dims.get('depth', dims.get('length', 50))
    
    # Four corners of bounding box
    corners = [
        pos,  # origin corner
        (pos[0] + along[0] * width, pos[1] + along[1] * width),
        (pos[0] + along[0] * width + perp[0] * depth, pos[1] + along[1] * width + perp[1] * depth),
        (pos[0] + perp[0] * depth, pos[1] + perp[1] * depth),
    ]
    return corners

def rotate_bbox(bbox, center, angle_deg):
    """Rotate bbox corners around center by angle (degrees, clockwise).
    
    Returns None if bbox is None or angle is 0/None.
    """
    if not bbox or not angle_deg:
        return bbox
    rad = math.radians(-angle_deg)  # negative for clockwise
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    result = []
    for p in bbox:
        dx, dy = p[0] - center[0], p[1] - center[1]
        result.append((
            center[0] + dx * cos_a - dy * sin_a,
            center[1] + dx * sin_a + dy * cos_a
        ))
    return result

def closest_point_on_bbox(bbox, point):
    """Find closest point on bounding box to a given point."""
    if not bbox:
        return None
    
    # Simple approach: check distance to each edge and find minimum
    min_dist = float('inf')
    closest = None
    
    for i in range(4):
        p1 = bbox[i]
        p2 = bbox[(i + 1) % 4]
        
        # Project point onto line segment
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            closest_on_seg = p1
        else:
            t = max(0, min(1, ((point[0] - p1[0]) * dx + (point[1] - p1[1]) * dy) / length_sq))
            closest_on_seg = (p1[0] + t * dx, p1[1] + t * dy)
        
        dist = math.sqrt((point[0] - closest_on_seg[0])**2 + (point[1] - closest_on_seg[1])**2)
        if dist < min_dist:
            min_dist = dist
            closest = closest_on_seg
    
    return closest, min_dist

def segment_to_segment_distance(p1, p2, p3, p4):
    """Minimum distance between two line segments (p1-p2) and (p3-p4)."""
    def point_to_segment_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            return math.sqrt((px - ax)**2 + (py - ay)**2)
        t = max(0, min(1, ((px - ax)*dx + (py - ay)*dy) / length_sq))
        proj_x, proj_y = ax + t*dx, ay + t*dy
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
    
    # Check all endpoints against the other segment
    d1 = point_to_segment_dist(p1[0], p1[1], p3[0], p3[1], p4[0], p4[1])
    d2 = point_to_segment_dist(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])
    d3 = point_to_segment_dist(p3[0], p3[1], p1[0], p1[1], p2[0], p2[1])
    d4 = point_to_segment_dist(p4[0], p4[1], p1[0], p1[1], p2[0], p2[1])
    return min(d1, d2, d3, d4)

def bbox_to_bbox_distance(bbox1, bbox2):
    """Minimum edge-to-edge distance between two bounding boxes."""
    if not bbox1 or not bbox2:
        return None
    
    min_dist = float('inf')
    for i in range(4):
        for j in range(4):
            d = segment_to_segment_distance(
                bbox1[i], bbox1[(i+1) % 4],
                bbox2[j], bbox2[(j+1) % 4]
            )
            min_dist = min(min_dist, d)
    return min_dist

def point_in_polygon(point, polygon, tolerance=5):
    """Check if point is inside polygon (with tolerance for boundary points).
    
    Uses ray casting but also checks if point is within tolerance of any edge.
    """
    x, y = point
    n = len(polygon)
    
    # First check if on or near any edge (within tolerance)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        
        # Distance from point to line segment
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            # Degenerate segment
            dist = math.sqrt((x - p1[0])**2 + (y - p1[1])**2)
        else:
            t = max(0, min(1, ((x - p1[0])*dx + (y - p1[1])*dy) / length_sq))
            proj_x = p1[0] + t * dx
            proj_y = p1[1] + t * dy
            dist = math.sqrt((x - proj_x)**2 + (y - proj_y)**2)
        
        if dist <= tolerance:
            return True  # On or near boundary - counts as inside
    
    # Standard ray casting for points clearly inside
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside

def bbox_overlaps(bbox1, bbox2):
    """Check if two oriented bounding boxes overlap using Separating Axis Theorem.
    
    Works correctly for rotated rectangles - no false positives from AABB approximation.
    """
    if not bbox1 or not bbox2:
        return False
    
    def get_edges(bbox):
        """Get edge vectors for the polygon."""
        edges = []
        for i in range(len(bbox)):
            p1, p2 = bbox[i], bbox[(i + 1) % len(bbox)]
            edges.append((p2[0] - p1[0], p2[1] - p1[1]))
        return edges
    
    def get_normals(edges):
        """Get perpendicular normals to edges (potential separating axes)."""
        normals = []
        for edge in edges:
            # Perpendicular: rotate 90°
            normals.append((-edge[1], edge[0]))
        return normals
    
    def project(bbox, axis):
        """Project all points onto axis, return (min, max)."""
        dots = [p[0] * axis[0] + p[1] * axis[1] for p in bbox]
        return min(dots), max(dots)
    
    def overlaps_on_axis(bbox1, bbox2, axis):
        """Check if projections overlap on given axis."""
        min1, max1 = project(bbox1, axis)
        min2, max2 = project(bbox2, axis)
        return max1 > min2 and max2 > min1
    
    # Get all potential separating axes (edge normals from both boxes)
    axes = get_normals(get_edges(bbox1)) + get_normals(get_edges(bbox2))
    
    # If we find ANY axis where projections don't overlap, boxes don't overlap
    for axis in axes:
        if not overlaps_on_axis(bbox1, bbox2, axis):
            return False
    
    # No separating axis found - boxes overlap
    return True

def validate_objects(objects, corners, room):
    """Check for objects outside room or overlapping. Returns list of warnings."""
    warnings = []
    
    # Build room polygon from corners in wall order (traced correctly)
    room_polygon = []
    walls = room.get('walls') or []
    if walls:
        # Get corner order from wall IDs
        for wall in walls:
            start = wall['id'].split('-')[0]
            if start in corners:
                room_polygon.append(corners[start])
    
    if len(room_polygon) < 3:
        # Fallback - can't validate
        return warnings
    
    # Check each object with bbox
    for obj in objects:
        if not obj.get('bbox'):
            continue
        
        bbox = obj['bbox']
        obj_id = obj['id']
        
        # Wall-mounted items are allowed to extend slightly outside room boundary
        # (they're on the wall, not on the floor)
        if obj.get('mount') == 'wall':
            continue  # Skip boundary check for wall-mounted items
        
        # Items on surfaces don't need floor boundary checks
        if obj.get('on'):
            continue  # Skip boundary check for on-surface items
        
        # Check if any corner of bbox is outside room
        for i, corner in enumerate(bbox):
            if not point_in_polygon(corner, room_polygon):
                warnings.append(f"# WARNING: {obj_id} extends outside room (corner {i+1} at {corner[0]:.0f},{corner[1]:.0f})")
                break  # One warning per object
    
    # Check for overlaps between objects
    # Skip overlap checks for items at different heights:
    # - wall-mounted vs floor-standing
    # - on-surface items vs floor items
    # - on-surface item vs its base object
    objects_with_bbox = [o for o in objects if o.get('bbox')]
    for i, obj1 in enumerate(objects_with_bbox):
        for obj2 in objects_with_bbox[i+1:]:
            # Rugs are flat - furniture standing on a rug is not a collision
            if obj1.get('item_type') == 'rug' or obj2.get('item_type') == 'rug':
                continue
            # Skip if one is wall-mounted and the other is floor-standing
            obj1_wall = obj1.get('mount') == 'wall'
            obj2_wall = obj2.get('mount') == 'wall'
            if obj1_wall != obj2_wall:
                continue  # Different mount types - no collision possible
            
            # Skip if either is on a surface (different height layer)
            obj1_on = obj1.get('on')
            obj2_on = obj2.get('on')
            if obj1_on or obj2_on:
                # Skip collision between surface item and floor items
                # Also skip if surface item is on the other object
                if obj1_on == obj2['id'] or obj2_on == obj1['id']:
                    continue  # Item is ON the other object
                if obj1_on and not obj2_on:
                    continue  # obj1 is on surface, obj2 is on floor
                if obj2_on and not obj1_on:
                    continue  # obj2 is on surface, obj1 is on floor
            
            if bbox_overlaps(obj1['bbox'], obj2['bbox']):
                # Show actual bounds for debugging
                def bounds(bbox):
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    return f"x:{min(xs):.0f}-{max(xs):.0f}, y:{min(ys):.0f}-{max(ys):.0f}"
                warnings.append(f"# WARNING: {obj1['id']} [{bounds(obj1['bbox'])}] overlaps with {obj2['id']} [{bounds(obj2['bbox'])}]")
    
    return warnings

def get_objects(room, corners, room_path=None):
    """Extract all positioned objects with absolute coordinates and bounding boxes."""
    objects = []
    
    # Built-ins
    for item in room.get('built_ins') or []:
        if 'position' in item and isinstance(item['position'], dict):
            pos = resolve_position(item['position'], corners, item.get('id'))
            dims = item.get('dimensions', {})
            mass = item.get('mass')  # kg
            bbox = None
            width_axis = None
            facing = None
            
            # STRICT: Require explicit orientation or facing (no wall-derived fallback)
            if item.get('orientation'):
                width_axis = item['orientation'].upper()  # N-S or E-W
                if width_axis not in ('N-S', 'E-W'):
                    print(f"# ERROR: {item['id']} has invalid orientation '{width_axis}' - must be N-S or E-W", file=sys.stderr)
                    continue
            if item.get('facing'):
                facing = item['facing'].lower()  # north/south/east/west
                if facing not in ('north', 'south', 'east', 'west'):
                    print(f"# ERROR: {item['id']} has invalid facing '{facing}' - must be north/south/east/west", file=sys.stderr)
                    continue
            
            # Compute bbox only if orientation is explicitly specified
            if pos and dims:
                if not width_axis and not facing:
                    print(f"# WARNING: {item['id']} has dimensions but no orientation/facing - bbox skipped", file=sys.stderr)
                elif facing:
                    perp_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
                    face_dir = perp_map[facing]
                    along = (-face_dir[1], face_dir[0])
                    perp = face_dir
                    bbox = compute_bbox(pos, dims, along, perp)
                elif width_axis:
                    if width_axis == 'N-S':
                        along = (0, 1)
                        perp = (1, 0)
                    else:  # E-W
                        along = (1, 0)
                        perp = (0, 1)
                    bbox = compute_bbox(pos, dims, along, perp)
            
            if pos:
                objects.append({
                    'type': 'built_in',
                    'id': item['id'],
                    'pos': pos,
                    'dims': dims,
                    'bbox': bbox,
                    'width_axis': width_axis,
                    'facing': facing,
                    'mass': mass,  # kg (None if unknown)
                    'mount': item.get('mount'),  # 'wall' for wall-mounted items
                    'item_type': detect_item_type(item, item['id']),
                    'zone': item.get('zone'),
                })
        elif 'wall' in item and 'position' in item:
            # Wall-mounted built-in
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length_val = math.sqrt(dx**2 + dy**2)
            unit = (dx/length_val, dy/length_val)
            # Perpendicular into room (rotate 90° counterclockwise)
            perp = (-unit[1], unit[0])
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            
            # Compute bbox if length and depth are specified
            bbox = None
            item_length = item.get('length')
            item_depth = item.get('depth')
            if item_length and item_depth:
                # Rectangle along wall, extending into room
                p1 = (x, y)  # start corner on wall
                p2 = (x + unit[0] * item_length, y + unit[1] * item_length)  # end along wall
                p3 = (p2[0] + perp[0] * item_depth, p2[1] + perp[1] * item_depth)  # into room
                p4 = (p1[0] + perp[0] * item_depth, p1[1] + perp[1] * item_depth)  # into room
                bbox = [p1, p2, p3, p4]
            
            objects.append({
                'type': 'built_in',
                'id': item['id'],
                'pos': (round(x), round(y)),
                'length': item_length,
                'depth': item_depth,
                'bbox': bbox,
                'mass': item.get('mass'),  # kg (None if unknown)
                'wall': wall_id,
                'wall_unit': unit,
                'wall_perp': perp,
                'item_type': detect_item_type(item, item['id']),
                'zone': item.get('zone'),
            })
    
    # Lighting (ceiling fixtures - point objects, no bbox)
    for item in room.get('lighting') or []:
        pos = resolve_position(item.get('position'), corners, item.get('id'))
        if pos:
            objects.append({
                'type': 'light',
                'id': item['id'],
                'pos': pos,
                'ceiling': item.get('ceiling'),
                'bbox': None,
                'mount': item.get('mount'),       # pendant/recessed/table/...
                'hang_height_cm': item.get('hang_height_cm'),
                'layer': item.get('layer'),       # ambient|task|accent (optional)
                'item_type': detect_item_type(item, item['id']) if not item.get('mount') else (
                    item['mount'] if item['mount'] in ITEM_TYPES else sniff_type(item['id'])),
            })
    
    # Furniture (with registry lookup for dimensions and mass)
    for item in room.get('furniture') or []:
        pos = resolve_position(item.get('position'), corners, item.get('id'))
        if pos:
            # Get dimensions and mass from registry or inline
            dims = item.get('dimensions', {})
            mass = item.get('mass')  # kg
            reg = None
            if room_path and item.get('registry'):
                reg = load_registry(room_path, item['registry'])
                if reg:
                    if not dims:
                        dims = reg.get('dimensions', {})
                    if mass is None:
                        mass = reg.get('mass')  # kg
            
            bbox = None
            width_axis = None
            facing = None
            
            # STRICT: Require explicit orientation or facing (no wall-derived fallback)
            if item.get('orientation'):
                width_axis = item['orientation'].upper()  # N-S or E-W
                if width_axis not in ('N-S', 'E-W'):
                    print(f"# ERROR: {item['id']} has invalid orientation '{width_axis}' - must be N-S or E-W", file=sys.stderr)
                    continue
            if item.get('facing'):
                facing = item['facing'].lower()  # north/south/east/west
                if facing not in ('north', 'south', 'east', 'west'):
                    print(f"# ERROR: {item['id']} has invalid facing '{facing}' - must be north/south/east/west", file=sys.stderr)
                    continue
            
            # Compute bbox only if orientation is explicitly specified
            rotation = item.get('rotation', 0)
            if dims:
                if not width_axis and not facing:
                    print(f"# WARNING: {item['id']} has dimensions but no orientation/facing - bbox skipped", file=sys.stderr)
                elif facing:
                    # Position is corner nearest to reference walls (consistent with orientation items)
                    # For facing items: width runs perpendicular to facing, depth projects in facing direction
                    perp_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
                    face_dir = perp_map[facing]
                    # along = perpendicular to facing (width runs along this axis)
                    along = (-face_dir[1], face_dir[0])
                    perp = face_dir
                    bbox = compute_bbox(pos, dims, along, perp)
                elif width_axis:
                    if width_axis == 'N-S':
                        along = (0, 1)
                        perp = (1, 0)
                    else:  # E-W
                        along = (1, 0)
                        perp = (0, 1)
                    bbox = compute_bbox(pos, dims, along, perp)
                
                # Apply rotation if specified
                if bbox and rotation:
                    # Rotate around bbox center
                    cx = sum(p[0] for p in bbox) / 4
                    cy = sum(p[1] for p in bbox) / 4
                    bbox = rotate_bbox(bbox, (cx, cy), rotation)
            
            # Screen diagonal (TV-01): item field wins, registry fallback
            screen_diagonal = item.get('screen_diagonal_in')
            if screen_diagonal is None and reg:
                screen_diagonal = reg.get('screen_diagonal_in')

            objects.append({
                'type': 'furniture',
                'id': item['id'],
                'pos': pos,
                'dims': dims,
                'bbox': bbox,
                'width_axis': width_axis,
                'facing': facing,
                'rotation': rotation,
                'registry': item.get('registry'),
                'mass': mass,  # kg (None if unknown)
                'mount': item.get('mount'),  # 'wall' for wall-mounted items
                'on': item.get('on'),  # base object ID for surface items
                'height': item.get('height'),  # cm AFFL for wall-mounted items
                'item_type': detect_item_type(item, item['id']),
                'zone': item.get('zone'),
                'screen_diagonal_in': screen_diagonal,
            })
    
    # Windows
    for item in room.get('windows') or []:
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete windows (notes-only entries)
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'window',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'width': item.get('width'),
            'wall': wall_id,
            'wall_unit': unit,
            'wall_perp': (-unit[1], unit[0]),  # into room
            'window_type': item.get('type'),   # e.g. sliding-door
        })
    
    # Outlets
    for item in room.get('outlets') or []:
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete outlets
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'outlet',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'height': item.get('height'),
            'outlet_type': item.get('type'),
        })
    
    # Openings (passages between rooms)
    for item in room.get('openings') or []:
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete openings (notes-only entries)
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'opening',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'width': item.get('width'),
            'to': item.get('to'),
            'has_door': item.get('has_door', False),
            'wall': wall_id,
            'wall_unit': unit,
            'wall_perp': (-unit[1], unit[0]),  # into room
        })
    
    # Heating
    for item in room.get('heating') or []:
        if 'wall' in item and 'position' in item:
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length = math.sqrt(dx**2 + dy**2)
            unit = (dx/length, dy/length)
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            objects.append({
                'type': 'heating',
                'id': item['id'],
                'pos': (round(x), round(y)),
                'length': item.get('length'),
                'wall': wall_id,
                'wall_unit': unit,
                'wall_perp': (-unit[1], unit[0]),  # into room
            })
    
    # Plumbing
    for item in room.get('plumbing') or []:
        if 'wall' in item and 'position' in item:
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length = math.sqrt(dx**2 + dy**2)
            unit = (dx/length, dy/length)
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            objects.append({
                'type': 'plumbing',
                'id': item['id'],
                'pos': (round(x), round(y)),
            })
    
    return objects

def distance(p1, p2):
    """Euclidean distance between two points."""
    return math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)

FACING_ANGLES = {
    'north': 90,
    'south': -90,
    'east': 0,
    'west': 180,
}

def normalize_angle(a):
    """Normalize angle to -180 to 180."""
    while a > 180: a -= 360
    while a < -180: a += 360
    return a

def view_from(objects, corners, viewer_pos, facing=None):
    """List objects visible from a position, sorted by distance to closest edge.
    
    If facing is specified (north/south/east/west), only show objects
    within 90° cone of that direction.
    
    Distance is to the closest point on the object's bounding box (if available),
    otherwise to the position point.
    """
    facing_angle = FACING_ANGLES.get(facing) if facing else None
    
    result = []
    for obj in objects:
        # Use closest edge if bbox available, otherwise position point
        if obj.get('bbox'):
            closest, d = closest_point_on_bbox(obj['bbox'], viewer_pos)
            # Angle to closest point
            angle = math.degrees(math.atan2(
                closest[1] - viewer_pos[1],
                closest[0] - viewer_pos[0]
            ))
        else:
            d = distance(viewer_pos, obj['pos'])
            angle = math.degrees(math.atan2(
                obj['pos'][1] - viewer_pos[1],
                obj['pos'][0] - viewer_pos[0]
            ))
        
        # Filter by facing direction if specified
        if facing_angle is not None:
            diff = abs(normalize_angle(angle - facing_angle))
            if diff > 45:  # outside 90° cone
                continue
        
        result.append({**obj, 'distance': round(d), 'angle': round(angle)})
    
    result.sort(key=lambda x: x['distance'])
    return result

# ---------------------------------------------------------------------------
# Rules engine (--check)
# ---------------------------------------------------------------------------

RULES_PATH = Path(__file__).parent / "rules" / "clearances.yaml"
SEVERITY_ORDER = {'ERROR': 0, 'WARN': 1, 'PASS': 2, 'SKIP': 3}

def load_rules():
    """Load canonical rule table from scripts/rules/clearances.yaml -> {id: rule}."""
    try:
        with open(RULES_PATH) as f:
            data = yaml.safe_load(f)
        return {r['id']: r for r in (data.get('rules') or [])}
    except Exception as e:
        note(f"# WARNING: could not load rules from {RULES_PATH}: {e}")
        return {}

def finding(severity, rule, message, items=None):
    """One rule finding. Rendered as 'SEVERITY RULE-ID: message'."""
    return {'severity': severity, 'rule': rule, 'message': message, 'items': items or []}

def room_polygon_pts(room, corners):
    """Room boundary polygon in wall order (same logic as validate_objects)."""
    polygon = []
    for wall in room.get('walls') or []:
        start = wall['id'].split('-')[0]
        if start in corners:
            polygon.append(corners[start])
    return polygon if len(polygon) >= 3 else None

def floor_obstacles(objects):
    """Floor-standing furniture/built-ins with bboxes (the things you walk around).

    Excludes wall-mounted items, on-surface items, and rugs (walkable).
    """
    result = []
    for o in objects:
        if o['type'] not in ('furniture', 'built_in'):
            continue
        if not o.get('bbox'):
            continue
        if o.get('mount') == 'wall':
            continue
        if o.get('on'):
            continue
        if o.get('item_type') == 'rug':
            continue
        result.append(o)
    return result

def bbox_aabb(bbox):
    """Axis-aligned bounds (minx, miny, maxx, maxy) of a bbox."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)

def bbox_center(bbox):
    return (sum(p[0] for p in bbox) / len(bbox), sum(p[1] for p in bbox) / len(bbox))

def item_height(obj):
    """Item height in cm from dims (registry-resolved), or None if unknown."""
    dims = obj.get('dims') or {}
    return dims.get('height')

def bbox_edges_outward(bbox):
    """Yield (p1, p2, outward_normal) for each bbox edge, handling either winding."""
    n = len(bbox)
    area2 = sum(bbox[i][0] * bbox[(i + 1) % n][1] - bbox[(i + 1) % n][0] * bbox[i][1]
                for i in range(n))
    ccw = area2 > 0
    for i in range(n):
        p1, p2 = bbox[i], bbox[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        d = (dx / length, dy / length)
        normal = (d[1], -d[0]) if ccw else (-d[1], d[0])
        yield p1, p2, normal

def segments_cross(p1, p2, p3, p4):
    """True if segments p1-p2 and p3-p4 intersect."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return False

def segment_intersects_bbox(p1, p2, bbox):
    """True if segment p1-p2 passes through a bbox."""
    if point_in_polygon(p1, bbox, tolerance=0.1) or point_in_polygon(p2, bbox, tolerance=0.1):
        return True
    n = len(bbox)
    for i in range(n):
        if segments_cross(p1, p2, bbox[i], bbox[(i + 1) % n]):
            return True
    return False

def ray_to_boundary(origin, direction, polygon):
    """Distance along a ray to the nearest polygon edge (None if no hit)."""
    best = None
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        denom = direction[0] * ey - direction[1] * ex
        if abs(denom) < 1e-9:
            continue
        ax_ox, ay_oy = a[0] - origin[0], a[1] - origin[1]
        t = (ax_ox * ey - ex * ay_oy) / denom
        s = (direction[1] * ax_ox - direction[0] * ay_oy) / denom
        if t > 0.5 and -1e-6 <= s <= 1 + 1e-6:
            best = t if best is None else min(best, t)
    return best

def edge_clearance(edge_p1, edge_p2, out_dir, obstacles, room_polygon, ignore_ids=()):
    """Min free distance in front of an edge, looking along out_dir.

    Considers obstacle bboxes whose projection overlaps the edge span, plus the
    room boundary (sampled rays). Returns (distance_cm, blocker_id_or_'wall').
    """
    ux, uy = edge_p2[0] - edge_p1[0], edge_p2[1] - edge_p1[1]
    span = math.hypot(ux, uy)
    if span < 1e-9:
        return (float('inf'), None)
    u = (ux / span, uy / span)
    v = out_dir
    best_d, best_id = float('inf'), None

    for o in obstacles:
        if o['id'] in ignore_ids or not o.get('bbox'):
            continue
        proj_u = [(c[0] - edge_p1[0]) * u[0] + (c[1] - edge_p1[1]) * u[1] for c in o['bbox']]
        proj_v = [(c[0] - edge_p1[0]) * v[0] + (c[1] - edge_p1[1]) * v[1] for c in o['bbox']]
        if max(proj_u) <= 1 or min(proj_u) >= span - 1:
            continue  # no overlap with the edge span
        if max(proj_v) <= 0.5:
            continue  # entirely behind the edge
        d = max(0.0, min(proj_v))
        if d < best_d:
            best_d, best_id = d, o['id']

    if room_polygon:
        for t in (0.1, 0.3, 0.5, 0.7, 0.9):
            origin = (edge_p1[0] + u[0] * span * t, edge_p1[1] + u[1] * span * t)
            d = ray_to_boundary(origin, v, room_polygon)
            if d is not None and d < best_d:
                best_d, best_id = d, 'wall'

    return best_d, best_id

# --- Corridor analysis (CIRC-01 / CIRC-02): 5cm raster + erosion binary search

GRID_CELL = 5  # cm

def build_circulation_grid(room_polygon, obstacles, doorway_segments):
    """Rasterize the room at 5cm. Returns grid dict with free mask + clearance field.

    Cells are free if inside the room polygon and not inside any obstacle bbox.
    Doorway segments (openings, balcony doors) punch a pocket through the wall so
    corridor width through a door is capped by the door width, not by the wall.
    Clearance = distance (cm) from each free cell to the nearest blocked cell.
    """
    margin = 2 * GRID_CELL + max([r for _, _, r in doorway_segments], default=0)
    minx = min(p[0] for p in room_polygon) - margin
    miny = min(p[1] for p in room_polygon) - margin
    maxx = max(p[0] for p in room_polygon) + margin
    maxy = max(p[1] for p in room_polygon) + margin
    nx = int(math.ceil((maxx - minx) / GRID_CELL))
    ny = int(math.ceil((maxy - miny) / GRID_CELL))

    def center(ix, iy):
        return (minx + (ix + 0.5) * GRID_CELL, miny + (iy + 0.5) * GRID_CELL)

    def point_seg_dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    obstacle_bboxes = [o['bbox'] for o in obstacles]
    free = [[False] * ny for _ in range(nx)]
    for ix in range(nx):
        for iy in range(ny):
            c = center(ix, iy)
            inside = point_in_polygon(c, room_polygon, tolerance=0.0)
            ok = inside
            if ok:
                for bbox in obstacle_bboxes:
                    if point_in_polygon(c, bbox, tolerance=0.1):
                        ok = False
                        break
            if not ok and not inside:
                # Doorway pocket: punch the wall open around each opening so the
                # corridor through a door is capped by the door width, not by
                # the wall raster. Never re-frees cells inside an obstacle.
                for seg_a, seg_b, radius in doorway_segments:
                    if point_seg_dist(c, seg_a, seg_b) <= radius:
                        ok = True
                        break
            free[ix][iy] = ok

    # Clearance field: multi-source Dijkstra from all blocked cells (8-neighbor)
    INF = float('inf')
    clearance = [[INF] * ny for _ in range(nx)]
    heap = []
    for ix in range(nx):
        for iy in range(ny):
            if not free[ix][iy]:
                clearance[ix][iy] = 0.0
                heap.append((0.0, ix, iy))
    heapq.heapify(heap)
    diag = GRID_CELL * math.sqrt(2)
    while heap:
        d, ix, iy = heapq.heappop(heap)
        if d > clearance[ix][iy]:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < nx and 0 <= jy < ny:
                    nd = d + (diag if dx and dy else GRID_CELL)
                    if nd < clearance[jx][jy]:
                        clearance[jx][jy] = nd
                        heapq.heappush(heap, (nd, jx, jy))

    return {'minx': minx, 'miny': miny, 'nx': nx, 'ny': ny,
            'free': free, 'clearance': clearance, 'center': center}

def nearest_free_cell(grid, point, max_radius_cells=8):
    """Snap a point to the nearest free grid cell. Returns (ix, iy) or None."""
    ix0 = int((point[0] - grid['minx']) / GRID_CELL)
    iy0 = int((point[1] - grid['miny']) / GRID_CELL)
    nx, ny, free = grid['nx'], grid['ny'], grid['free']
    for r in range(max_radius_cells + 1):
        best = None
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                jx, jy = ix0 + dx, iy0 + dy
                if 0 <= jx < nx and 0 <= jy < ny and free[jx][jy]:
                    c = grid['center'](jx, jy)
                    d = math.hypot(c[0] - point[0], c[1] - point[1])
                    if best is None or d < best[0]:
                        best = (d, jx, jy)
        if best:
            return (best[1], best[2])
    return None

def _path_exists(grid, start, goal, radius):
    """BFS over free cells with clearance >= radius (erosion by radius)."""
    from collections import deque
    nx, ny = grid['nx'], grid['ny']
    free, clearance = grid['free'], grid['clearance']
    if clearance[start[0]][start[1]] < radius or clearance[goal[0]][goal[1]] < radius:
        return False
    seen = [[False] * ny for _ in range(nx)]
    queue = deque([start])
    seen[start[0]][start[1]] = True
    while queue:
        ix, iy = queue.popleft()
        if (ix, iy) == goal:
            return True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                jx, jy = ix + dx, iy + dy
                if (0 <= jx < nx and 0 <= jy < ny and not seen[jx][jy]
                        and free[jx][jy] and clearance[jx][jy] >= radius):
                    seen[jx][jy] = True
                    queue.append((jx, jy))
    return False

def corridor_width(grid, point_a, point_b):
    """Widest corridor (cm) between two points: binary-search the max erosion
    radius for which a BFS path still exists. Returns None if no path at all."""
    start = nearest_free_cell(grid, point_a)
    goal = nearest_free_cell(grid, point_b)
    if start is None or goal is None:
        return None
    if not _path_exists(grid, start, goal, 0):
        return None
    lo = 0.0
    hi = min(grid['clearance'][start[0]][start[1]],
             grid['clearance'][goal[0]][goal[1]]) + GRID_CELL
    while hi - lo > 1.0:
        mid = (lo + hi) / 2
        if _path_exists(grid, start, goal, mid):
            lo = mid
        else:
            hi = mid
    return 2 * lo

def circulation_endpoints(objects):
    """Openings + balcony-door style windows usable as circulation endpoints."""
    eps = []
    for o in objects:
        if o['type'] == 'opening' and o.get('width'):
            eps.append(o)
        elif (o['type'] == 'window' and o.get('width')
              and o.get('window_type') in ('sliding-door', 'balcony-door', 'french-door', 'door')):
            eps.append(o)
    return eps

def endpoint_segment(ep):
    """Wall segment (a, b, pocket_radius) of an opening/window endpoint.

    pocket_radius = half the opening width: the wall raster is punched open
    that deep so a corridor through the door is capped by the door width."""
    unit = ep['wall_unit']
    a = ep['pos']
    b = (a[0] + unit[0] * ep['width'], a[1] + unit[1] * ep['width'])
    return a, b, max(2 * GRID_CELL, ep['width'] / 2)

def endpoint_inset_point(ep, inset=10):
    """Midpoint of an opening/window, nudged into the room."""
    unit, perp = ep['wall_unit'], ep['wall_perp']
    half = (ep.get('width') or 0) / 2
    return (ep['pos'][0] + unit[0] * half + perp[0] * inset,
            ep['pos'][1] + unit[1] * half + perp[1] * inset)

# --- Individual rule checks. Each appends finding() dicts to `findings`.

def by_item_type(objects, *types):
    return [o for o in objects
            if o['type'] in ('furniture', 'built_in') and o.get('item_type') in types]

def check_seating(objects, rules, findings):
    """SEAT-01 sofa/armchair <-> coffee table; SEAT-02 conversation spacing."""
    seats = [o for o in by_item_type(objects, 'sofa', 'armchair') if o.get('bbox')]
    r1 = rules.get('SEAT-01')
    if r1:
        tables = [o for o in by_item_type(objects, 'coffee-table') if o.get('bbox')]
        for s in seats:
            if not tables:
                break
            t = min(tables, key=lambda t: bbox_to_bbox_distance(s['bbox'], t['bbox']))
            gap = bbox_to_bbox_distance(s['bbox'], t['bbox'])
            lo, hi = r1.get('ideal_range_cm', [35, 46])
            pair = f"{s['id']}↔{t['id']}"
            if gap < r1['min_cm']:
                findings.append(finding('ERROR', 'SEAT-01',
                    f"{pair} gap {gap:.0f}cm < {r1['min_cm']}cm (ideal {lo}–{hi}cm)",
                    [s['id'], t['id']]))
            elif gap < lo:
                findings.append(finding('WARN', 'SEAT-01',
                    f"{pair} gap {gap:.0f}cm below ideal {lo}–{hi}cm (min {r1['min_cm']}cm)",
                    [s['id'], t['id']]))
            elif gap > r1.get('warn_above_cm', 50):
                findings.append(finding('WARN', 'SEAT-01',
                    f"{pair} gap {gap:.0f}cm > {r1.get('warn_above_cm', 50)}cm — "
                    f"table out of reach (ideal {lo}–{hi}cm)", [s['id'], t['id']]))
    r2 = rules.get('SEAT-02')
    if r2 and len(seats) >= 2:
        max_ideal = r2.get('max_ideal_cm', 300)
        err_above = r2.get('error_above_cm', 360)
        for i, a in enumerate(seats):
            for b in seats[i + 1:]:
                if a.get('zone') and b.get('zone') and a['zone'] != b['zone']:
                    continue  # different conversation zones
                d = bbox_to_bbox_distance(a['bbox'], b['bbox'])
                pair = f"{a['id']}↔{b['id']}"
                if d > err_above:
                    findings.append(finding('ERROR', 'SEAT-02',
                        f"{pair} seats {d:.0f}cm apart > {err_above}cm "
                        f"(conversation max {max_ideal}cm)", [a['id'], b['id']]))
                elif d > max_ideal:
                    findings.append(finding('WARN', 'SEAT-02',
                        f"{pair} seats {d:.0f}cm apart > conversation max {max_ideal}cm",
                        [a['id'], b['id']]))

def check_dining(room, objects, rules, findings, room_polygon, routes_segments):
    """DIN-01 chair pull-out side; DIN-02 circulation side behind chairs."""
    tables = [o for o in by_item_type(objects, 'dining-table') if o.get('bbox')]
    if not tables:
        return
    chairs = [o for o in by_item_type(objects, 'dining-chair') if o.get('bbox')]
    obstacles = floor_obstacles(objects)
    r1 = rules.get('DIN-01')
    for t in tables:
        ignore = {t['id']} | {c['id'] for c in chairs}
        if r1:
            for p1, p2, normal in bbox_edges_outward(t['bbox']):
                # Seated side = a dining chair sits beyond this edge
                span = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                u = ((p2[0] - p1[0]) / span, (p2[1] - p1[1]) / span)
                seated = False
                for c in chairs:
                    cx, cy = bbox_center(c['bbox'])
                    pu = (cx - p1[0]) * u[0] + (cy - p1[1]) * u[1]
                    pv = (cx - p1[0]) * normal[0] + (cy - p1[1]) * normal[1]
                    if -10 <= pu <= span + 10 and 0 < pv <= 100:
                        seated = True
                        break
                if not seated:
                    continue
                d, blocker = edge_clearance(p1, p2, normal, obstacles, room_polygon, ignore)
                side = vec_to_cardinal(normal)
                if d < r1['min_cm']:
                    findings.append(finding('ERROR', 'DIN-01',
                        f"{t['id']} {side} side clearance {d:.0f}cm < {r1['min_cm']}cm "
                        f"(chair pull-out, ideal {r1['ideal_cm']}cm)",
                        [t['id']] + ([blocker] if blocker and blocker != 'wall' else [])))
                elif d < r1['ideal_cm']:
                    findings.append(finding('WARN', 'DIN-01',
                        f"{t['id']} {side} side clearance {d:.0f}cm below ideal "
                        f"{r1['ideal_cm']}cm (min {r1['min_cm']}cm)",
                        [t['id']] + ([blocker] if blocker and blocker != 'wall' else [])))
        r2 = rules.get('DIN-02')
        if r2:
            if not routes_segments:
                findings.append(finding('SKIP', 'DIN-02',
                    f"no circulation: routes declared — cannot tell which side of "
                    f"{t['id']} is a walkway", [t['id']]))
            for route_id, seg_a, seg_b in routes_segments:
                # Which table side does the route pass?
                best = None
                for p1, p2, normal in bbox_edges_outward(t['bbox']):
                    d = segment_to_segment_distance(seg_a, seg_b, p1, p2)
                    if best is None or d < best[0]:
                        best = (d, p1, p2, normal)
                if best is None or best[0] > 250:
                    continue  # route doesn't pass this table
                _, p1, p2, normal = best
                d, blocker = edge_clearance(p1, p2, normal, obstacles, room_polygon, ignore)
                side = vec_to_cardinal(normal)
                if d < r2['min_cm']:
                    findings.append(finding('ERROR', 'DIN-02',
                        f"{t['id']} {side} side clearance {d:.0f}cm < {r2['min_cm']}cm "
                        f"on route '{route_id}' (circulation side, ideal {r2['ideal_cm']}cm)",
                        [t['id']]))
                elif d < r2['ideal_cm']:
                    findings.append(finding('WARN', 'DIN-02',
                        f"{t['id']} {side} side clearance {d:.0f}cm below ideal "
                        f"{r2['ideal_cm']}cm on route '{route_id}' (min {r2['min_cm']}cm)",
                        [t['id']]))

def check_bed(objects, rules, findings, room_polygon):
    """BED-01 side clearances; BED-02 foot clearance when it is a passage."""
    beds = [o for o in by_item_type(objects, 'bed') if o.get('bbox')]
    if not beds:
        return
    obstacles = floor_obstacles(objects)
    openings = circulation_endpoints(objects)
    r1, r2 = rules.get('BED-01'), rules.get('BED-02')
    bedside_ids = {o['id'] for o in by_item_type(objects, 'nightstand', 'side-table')}
    for bed in beds:
        facing = bed.get('facing')
        face_vec = DIRECTIONS.get(facing) if facing else None
        width = (bed.get('dims') or {}).get('width', 0)
        ideal_side = r1.get('ideal_cm', 75) if r1 else 75
        if width >= 180:
            ideal_side = r1.get('ideal_king_cm', 91)
        elif width >= 150:
            ideal_side = r1.get('ideal_queen_cm', 76)
        for p1, p2, normal in bbox_edges_outward(bed['bbox']):
            edge_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if face_vec:
                dot = normal[0] * face_vec[0] + normal[1] * face_vec[1]
                kind = 'foot' if dot > 0.7 else ('head' if dot < -0.7 else 'side')
            else:
                # No facing: longer edges are the sides
                dims = bed.get('dims') or {}
                long_side = max(dims.get('width', 0), dims.get('depth', 0))
                kind = 'side' if abs(edge_len - long_side) < 1 else 'foot?'
            # Measure past bedside furniture (nightstands sit beside the bed by design)
            d, blocker = edge_clearance(p1, p2, normal, obstacles, room_polygon,
                                        {bed['id']} | bedside_ids)
            side = vec_to_cardinal(normal)
            if kind == 'side' and r1:
                if d < 10 and blocker == 'wall':
                    continue  # against a wall — unused side
                if d < r1['min_cm']:
                    findings.append(finding('ERROR', 'BED-01',
                        f"{bed['id']} {side} side clearance {d:.0f}cm < {r1['min_cm']}cm "
                        f"(ideal {ideal_side}cm)", [bed['id']]))
                elif d < ideal_side:
                    findings.append(finding('WARN', 'BED-01',
                        f"{bed['id']} {side} side clearance {d:.0f}cm below ideal "
                        f"{ideal_side}cm (min {r1['min_cm']}cm)", [bed['id']]))
            elif kind in ('foot', 'foot?') and r2:
                # Passage heuristic: an opening lies beyond the foot edge
                passage = None
                for ep in openings:
                    mp = endpoint_inset_point(ep, inset=0)
                    pv = (mp[0] - p1[0]) * normal[0] + (mp[1] - p1[1]) * normal[1]
                    if pv > 1:
                        passage = ep['id']
                        break
                if not passage:
                    continue
                if d < r2['min_cm']:
                    findings.append(finding('ERROR', 'BED-02',
                        f"{bed['id']} foot clearance {d:.0f}cm < {r2['min_cm']}cm "
                        f"(passage to {passage}, ideal {r2['ideal_cm']}cm)", [bed['id']]))
                elif d < r2['ideal_cm']:
                    findings.append(finding('WARN', 'BED-02',
                        f"{bed['id']} foot clearance {d:.0f}cm below ideal {r2['ideal_cm']}cm "
                        f"(passage to {passage}, min {r2['min_cm']}cm)", [bed['id']]))

def check_kitchen(objects, rules, findings, room_polygon):
    """KIT-01 work aisle in front of kitchen runs / islands."""
    r = rules.get('KIT-01')
    if not r:
        return
    kitchens = [o for o in by_item_type(objects, 'kitchen', 'island') if o.get('bbox')]
    obstacles = floor_obstacles(objects)
    for k in kitchens:
        front_dir = k.get('wall_perp') or (DIRECTIONS.get(k['facing']) if k.get('facing') else None)
        for p1, p2, normal in bbox_edges_outward(k['bbox']):
            if front_dir:
                if normal[0] * front_dir[0] + normal[1] * front_dir[1] < 0.7:
                    continue  # only the counter-facing edge
            d, blocker = edge_clearance(p1, p2, normal, obstacles, room_polygon, {k['id']})
            if front_dir is None and d < 5 and blocker == 'wall':
                continue  # edge against a wall (island heuristic)
            what = blocker if blocker and blocker != 'wall' else 'wall'
            if d < r['min_cm']:
                findings.append(finding('ERROR', 'KIT-01',
                    f"{k['id']} work aisle {d:.0f}cm < {r['min_cm']}cm "
                    f"({what}, ideal {r['ideal_cm']}cm)",
                    [k['id']] + ([blocker] if blocker and blocker != 'wall' else [])))
            elif d < r['ideal_cm']:
                findings.append(finding('WARN', 'KIT-01',
                    f"{k['id']} work aisle {d:.0f}cm below ideal {r['ideal_cm']}cm "
                    f"({what}, min {r['min_cm']}cm)",
                    [k['id']] + ([blocker] if blocker and blocker != 'wall' else [])))

def check_heating(objects, rules, findings):
    """HEAT-01 radiator not blocked (WARN only)."""
    r = rules.get('HEAT-01')
    if not r:
        return
    obstacles = floor_obstacles(objects)
    for h in objects:
        if h['type'] != 'heating' or not h.get('length') or not h.get('wall_unit'):
            continue
        unit, perp = h['wall_unit'], h['wall_perp']
        p1 = h['pos']
        p2 = (p1[0] + unit[0] * h['length'], p1[1] + unit[1] * h['length'])
        d, blocker = edge_clearance(p1, p2, perp, obstacles, None)
        if blocker is None:
            continue
        if d < r['min_cm']:
            findings.append(finding('WARN', 'HEAT-01',
                f"{h['id']} blocked — {blocker} {d:.0f}cm in front (min {r['min_cm']}cm, "
                f"ideal {r['ideal_cm']}cm)", [h['id'], blocker]))
        elif d < r['ideal_cm']:
            findings.append(finding('WARN', 'HEAT-01',
                f"{h['id']} only {d:.0f}cm clear in front of {blocker} "
                f"(ideal {r['ideal_cm']}cm)", [h['id'], blocker]))

def quarter_arc_polygon(center, dir_from, dir_to, radius, segments=12):
    """Quarter-circle door swing polygon: center + ~12 arc points."""
    cross = dir_from[0] * dir_to[1] - dir_from[1] * dir_to[0]
    sign = 1 if cross >= 0 else -1
    pts = [center]
    for i in range(segments + 1):
        theta = sign * (math.pi / 2) * i / segments
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        rx = dir_from[0] * cos_t - dir_from[1] * sin_t
        ry = dir_from[0] * sin_t + dir_from[1] * cos_t
        pts.append((center[0] + rx * radius, center[1] + ry * radius))
    return pts

def check_doors(objects, rules, findings):
    """DOOR-01 door swing arcs vs floor-standing items (both hinge sides)."""
    if 'DOOR-01' not in rules:
        return
    obstacles = floor_obstacles(objects)
    for op in objects:
        if op['type'] != 'opening' or not op.get('has_door'):
            continue
        if not op.get('width'):
            findings.append(finding('SKIP', 'DOOR-01',
                f"{op['id']} has no width — cannot model door swing", [op['id']]))
            continue
        unit, perp = op['wall_unit'], op['wall_perp']
        width = op['width']
        start = op['pos']
        end = (start[0] + unit[0] * width, start[1] + unit[1] * width)
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        hinges = [(start, unit), (end, (-unit[0], -unit[1]))]
        blocked = []
        for hinge, panel_dir in hinges:
            arc = quarter_arc_polygon(hinge, panel_dir, perp, width)
            blockers = [o['id'] for o in obstacles
                        if o['id'] != op['id'] and bbox_overlaps(arc, o['bbox'])]
            side = vec_to_cardinal((hinge[0] - mid[0], hinge[1] - mid[1])) if width else '?'
            blocked.append((side, blockers))
        both_blocked = all(b for _, b in blocked)
        if both_blocked:
            detail = "; ".join(f"{side} hinge: {', '.join(b)}" for side, b in blocked)
            items = sorted({i for _, b in blocked for i in b})
            findings.append(finding('ERROR', 'DOOR-01',
                f"{op['id']} door swing blocked on both sides ({detail})",
                [op['id']] + items))
        elif any(b for _, b in blocked):
            (bad_side, blockers) = next((s, b) for s, b in blocked if b)
            free_side = next(s for s, b in blocked if not b)
            findings.append(finding('WARN', 'DOOR-01',
                f"{op['id']} swing blocked when hinged {bad_side} "
                f"({', '.join(blockers)}); {free_side} hinge is free",
                [op['id']] + blockers))

def check_windows(objects, rules, findings, room_polygon):
    """WIN-01 clear approach in front of windows / balcony doors."""
    r = rules.get('WIN-01')
    if not r:
        return
    obstacles = floor_obstacles(objects)
    for w in objects:
        if w['type'] != 'window' or not w.get('width'):
            continue
        wtype = (w.get('window_type') or '').lower()
        if wtype in ('fixed', 'non-operable'):
            findings.append(finding('SKIP', 'WIN-01',
                f"{w['id']} is a fixed pane — no approach required", [w['id']]))
            continue
        unit, perp = w['wall_unit'], w['wall_perp']
        p1 = w['pos']
        p2 = (p1[0] + unit[0] * w['width'], p1[1] + unit[1] * w['width'])
        d, blocker = edge_clearance(p1, p2, perp, obstacles, room_polygon)
        if blocker is None or blocker == 'wall':
            continue  # nothing in front (opposite wall doesn't block access)
        if d < r['min_cm']:
            findings.append(finding('ERROR', 'WIN-01',
                f"{w['id']} approach {d:.0f}cm < {r['min_cm']}cm "
                f"({blocker} in front, ideal {r['ideal_cm']}cm)", [w['id'], blocker]))
        elif d < r['ideal_cm']:
            findings.append(finding('WARN', 'WIN-01',
                f"{w['id']} approach {d:.0f}cm below ideal {r['ideal_cm']}cm "
                f"({blocker} in front, min {r['min_cm']}cm)", [w['id'], blocker]))

def check_tv(objects, rules, findings):
    """TV-01 viewing distance vs screen diagonal (SKIP without diagonal)."""
    r = rules.get('TV-01')
    if not r:
        return
    tvs = [o for o in by_item_type(objects, 'tv') if o.get('bbox')]
    seats = [o for o in by_item_type(objects, 'sofa', 'armchair') if o.get('bbox')]
    for tv in tvs:
        diag = tv.get('screen_diagonal_in')
        if not diag:
            findings.append(finding('SKIP', 'TV-01',
                f"no screen_diagonal_in on {tv['id']}", [tv['id']]))
            continue
        if not seats:
            findings.append(finding('SKIP', 'TV-01',
                f"no sofa/armchair to measure viewing distance for {tv['id']}", [tv['id']]))
            continue
        # Only seats that can actually watch this screen count as viewing seats:
        # inside the screen's ±60° cone, and (when the seat has a facing) turned
        # no more than ~35° away from the screen (THX off-axis limit).
        tv_face = DIRECTIONS.get((tv.get('facing') or '').lower())
        tvc = bbox_center(tv['bbox'])
        viewing = []
        for s in seats:
            sc = bbox_center(s['bbox'])
            vx, vy = sc[0] - tvc[0], sc[1] - tvc[1]
            norm = math.hypot(vx, vy)
            if norm < 1e-9:
                continue
            vx, vy = vx / norm, vy / norm
            if tv_face and (vx * tv_face[0] + vy * tv_face[1]) < 0.5:
                continue  # seat outside the screen's cone
            s_face = DIRECTIONS.get((s.get('facing') or '').lower())
            if s_face and (-vx * s_face[0] - vy * s_face[1]) < 0.82:
                continue  # screen more than ~35° off the seat's axis
            viewing.append(s)
        if not viewing:
            findings.append(finding('SKIP', 'TV-01',
                f"no seating oriented toward {tv['id']} ({diag}\") — "
                f"not positioned for primary viewing", [tv['id']]))
            continue
        seat = min(viewing, key=lambda s: bbox_to_bbox_distance(tv['bbox'], s['bbox']))
        d = bbox_to_bbox_distance(tv['bbox'], seat['bbox'])
        diag_cm = diag * 2.54
        ratio = d / diag_cm
        lo, hi = r.get('ideal_ratio_range', [1.2, 2.5])
        pair = f"{tv['id']}↔{seat['id']}"
        if ratio < r.get('min_ratio', 1.0):
            findings.append(finding('ERROR', 'TV-01',
                f"{pair} viewing distance {d:.0f}cm = {ratio:.1f}× diagonal "
                f"({diag}\" = {diag_cm:.0f}cm) < 1.0× minimum", [tv['id'], seat['id']]))
        elif ratio < lo or ratio > hi:
            findings.append(finding('WARN', 'TV-01',
                f"{pair} viewing distance {d:.0f}cm = {ratio:.1f}× diagonal "
                f"({diag}\" = {diag_cm:.0f}cm), outside ideal {lo}–{hi}×",
                [tv['id'], seat['id']]))

def check_proportions(room, corners, objects, rules, findings):
    """PROP-01 sofa vs its wall; PROP-02 coffee table vs sofa."""
    sofas = [o for o in by_item_type(objects, 'sofa') if o.get('bbox') and o.get('dims')]
    walls = room.get('walls') or []
    r1 = rules.get('PROP-01')
    if r1 and sofas and walls:
        for sofa in sofas:
            # Back edge midpoint (opposite facing), else bbox center
            probe = bbox_center(sofa['bbox'])
            if sofa.get('facing'):
                fv = DIRECTIONS[sofa['facing']]
                for p1, p2, normal in bbox_edges_outward(sofa['bbox']):
                    if normal[0] * -fv[0] + normal[1] * -fv[1] > 0.7:
                        probe = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        break
            best = None
            for wall in walls:
                start, end = wall['id'].split('-')
                d = segment_to_segment_distance(probe, probe, corners[start], corners[end])
                if best is None or d < best[0]:
                    best = (d, wall)
            if best[0] > 40:
                findings.append(finding('SKIP', 'PROP-01',
                    f"{sofa['id']} floats free of walls (back edge {best[0]:.0f}cm "
                    f"from nearest wall) — wall-proportion rule not applicable",
                    [sofa['id']]))
                continue
            wall = best[1]
            wall_len = wall['length']
            width = sofa['dims'].get('width', sofa['dims'].get('length', 0))
            pct = 100 * width / wall_len
            lo, hi = r1.get('ideal_range_pct', [60, 75])
            detail = f"{sofa['id']} {width}cm = {pct:.0f}% of wall {wall['id']} ({wall_len}cm)"
            if pct < r1['min_pct']:
                findings.append(finding('ERROR', 'PROP-01',
                    f"{detail} < {r1['min_pct']}% (ideal {lo}–{hi}%)", [sofa['id']]))
            elif pct < lo:
                findings.append(finding('WARN', 'PROP-01',
                    f"{detail}, below ideal {lo}–{hi}%", [sofa['id']]))
            elif pct > r1.get('warn_above_pct', 85):
                findings.append(finding('WARN', 'PROP-01',
                    f"{detail} > {r1.get('warn_above_pct', 85)}% — wall overloaded "
                    f"(ideal {lo}–{hi}%)", [sofa['id']]))
            elif pct > hi:
                findings.append(finding('WARN', 'PROP-01',
                    f"{detail}, above ideal {lo}–{hi}%", [sofa['id']]))
    r2 = rules.get('PROP-02')
    if r2 and sofas:
        tables = [o for o in by_item_type(objects, 'coffee-table')
                  if o.get('bbox') and o.get('dims')]
        for t in tables:
            sofa = min(sofas, key=lambda s: bbox_to_bbox_distance(t['bbox'], s['bbox']))
            t_w = t['dims'].get('width', t['dims'].get('length', 0))
            s_w = sofa['dims'].get('width', sofa['dims'].get('length', 0))
            if not t_w or not s_w:
                continue
            pct = 100 * t_w / s_w
            lo, hi = r2.get('ideal_range_pct', [55, 75])
            detail = f"{t['id']} {t_w}cm = {pct:.0f}% of {sofa['id']} width ({s_w}cm)"
            if pct < r2['min_pct']:
                findings.append(finding('ERROR', 'PROP-02',
                    f"{detail} < {r2['min_pct']}% (ideal {lo}–{hi}%)", [t['id'], sofa['id']]))
            elif pct < lo:
                findings.append(finding('WARN', 'PROP-02',
                    f"{detail}, below ideal {lo}–{hi}%", [t['id'], sofa['id']]))
            elif pct > hi:
                findings.append(finding('WARN', 'PROP-02',
                    f"{detail}, above ideal {lo}–{hi}%", [t['id'], sofa['id']]))

def check_rugs(room, corners, objects, rules, findings):
    """RUG-01 / RUG-02 — only when a rug item has dimensions and a bbox."""
    rugs = [o for o in by_item_type(objects, 'rug') if o.get('bbox')]
    if not rugs:
        for rid in ('RUG-01', 'RUG-02'):
            if rid in rules:
                findings.append(finding('SKIP', rid,
                    "no rug item with dimensions", []))
        return
    dining = [o for o in by_item_type(objects, 'dining-table') if o.get('bbox')]
    walls = room.get('walls') or []
    for rug in rugs:
        table = next((t for t in dining if bbox_overlaps(rug['bbox'], t['bbox'])), None)
        if table and 'RUG-02' in rules:
            r = rules['RUG-02']
            min_ext, tight_side = float('inf'), None
            for p1, p2, normal in bbox_edges_outward(rug['bbox']):
                ext = min((p1[0] - c[0]) * normal[0] + (p1[1] - c[1]) * normal[1]
                          for c in table['bbox'])
                if ext < min_ext:
                    min_ext, tight_side = ext, vec_to_cardinal(normal)
            if min_ext < r['min_cm']:
                findings.append(finding('ERROR', 'RUG-02',
                    f"{rug['id']} extends {min_ext:.0f}cm beyond {table['id']} on "
                    f"{tight_side} side < {r['min_cm']}cm — chairs slip off rug "
                    f"(ideal {r['ideal_cm']}cm)", [rug['id'], table['id']]))
            elif min_ext < r['ideal_cm']:
                findings.append(finding('WARN', 'RUG-02',
                    f"{rug['id']} extends {min_ext:.0f}cm beyond {table['id']} on "
                    f"{tight_side} side, below ideal {r['ideal_cm']}cm "
                    f"(min {r['min_cm']}cm)", [rug['id'], table['id']]))
        elif 'RUG-01' in rules and walls:
            r = rules['RUG-01']
            best = None
            for wall in walls:
                start, end = wall['id'].split('-')
                d = min(segment_to_segment_distance(
                            rug['bbox'][i], rug['bbox'][(i + 1) % 4],
                            corners[start], corners[end]) for i in range(4))
                if best is None or d < best[0]:
                    best = (d, wall['id'])
            d, wall_id = best
            lo, hi = r.get('ideal_range_cm', [30, 60])
            if d < r['min_cm']:
                findings.append(finding('ERROR', 'RUG-01',
                    f"{rug['id']} bare-floor border {d:.0f}cm to wall {wall_id} "
                    f"< {r['min_cm']}cm (ideal {lo}–{hi}cm)", [rug['id']]))
            elif d < lo:
                findings.append(finding('WARN', 'RUG-01',
                    f"{rug['id']} bare-floor border {d:.0f}cm to wall {wall_id}, "
                    f"below ideal {lo}–{hi}cm (min {r['min_cm']}cm)", [rug['id']]))

def check_pendants(objects, rules, findings):
    """LIGHT-01 pendant height above table surface (needs hang_height_cm)."""
    r = rules.get('LIGHT-01')
    if not r:
        return
    surfaces = [o for o in objects if o.get('bbox') and (o.get('dims') or {}).get('height')
                and o.get('item_type') in ('dining-table', 'coffee-table', 'side-table',
                                           'desk', 'kitchen', 'island')]
    for light in objects:
        if light['type'] != 'light' or light.get('mount') != 'pendant':
            continue
        table = next((s for s in surfaces
                      if point_in_polygon(light['pos'], s['bbox'], tolerance=1)), None)
        if table is None:
            continue  # pendant not over a known surface
        hang = light.get('hang_height_cm')
        if hang is None:
            findings.append(finding('SKIP', 'LIGHT-01',
                f"no hang_height_cm on {light['id']}", [light['id']]))
            continue
        clear = hang - table['dims']['height']
        lo, hi = r.get('ideal_range_cm', [76, 91])
        if clear < r['min_cm']:
            findings.append(finding('ERROR', 'LIGHT-01',
                f"{light['id']} {clear:.0f}cm above {table['id']} surface "
                f"< {r['min_cm']}cm (ideal {lo}–{hi}cm)", [light['id'], table['id']]))
        elif clear > hi:
            findings.append(finding('WARN', 'LIGHT-01',
                f"{light['id']} {clear:.0f}cm above {table['id']} surface, "
                f"above ideal {lo}–{hi}cm", [light['id'], table['id']]))

def check_circulation(room, objects, rules, findings, grid):
    """CIRC-01 opening-pair corridors + declared circulation routes (CIRC-02).

    Returns the route segments (for DIN-02)."""
    endpoints = circulation_endpoints(objects)
    by_id = {e['id']: e for e in endpoints}
    r1 = rules.get('CIRC-01')
    if r1:
        if len(endpoints) < 2:
            findings.append(finding('SKIP', 'CIRC-01',
                "fewer than two openings — no door-to-door routes to check", []))
        elif grid is None:
            findings.append(finding('SKIP', 'CIRC-01',
                "room polygon unavailable — cannot rasterize", []))
        else:
            for i, a in enumerate(endpoints):
                for b in endpoints[i + 1:]:
                    width = corridor_width(grid, endpoint_inset_point(a),
                                           endpoint_inset_point(b))
                    pair = f"{a['id']}→{b['id']}"
                    if width is None:
                        findings.append(finding('ERROR', 'CIRC-01',
                            f"{pair} corridor blocked — no clear path "
                            f"(min {r1['min_cm']}cm)", [a['id'], b['id']]))
                    elif width < r1['min_cm']:
                        findings.append(finding('ERROR', 'CIRC-01',
                            f"{pair} corridor {width:.0f}cm < {r1['min_cm']}cm "
                            f"(main route, ideal {r1['ideal_cm']}cm)", [a['id'], b['id']]))
                    elif width < r1['ideal_cm']:
                        findings.append(finding('WARN', 'CIRC-01',
                            f"{pair} corridor {width:.0f}cm below ideal "
                            f"{r1['ideal_cm']}cm (min {r1['min_cm']}cm)", [a['id'], b['id']]))
                    else:
                        findings.append(finding('PASS', 'CIRC-01',
                            f"{pair} corridor {width:.0f}cm "
                            f"(min {r1['min_cm']}cm, ideal {r1['ideal_cm']}cm)",
                            [a['id'], b['id']]))

    # Declared routes
    raw_routes = room.get('circulation')
    routes = raw_routes or []
    routes_segments = []
    if not routes:
        if 'CIRC-02' in rules:
            if raw_routes is None:
                findings.append(finding('SKIP', 'CIRC-02',
                    "circulation: not specified — run /planhaus:zone", []))
            else:
                findings.append(finding('SKIP', 'CIRC-02',
                    "circulation: declared empty — no door-to-door routes "
                    "in this room", []))
        return routes_segments
    all_by_id = {o['id']: o for o in objects}
    for route in routes:
        rid = route.get('id', f"{route.get('from')}→{route.get('to')}")
        rule_id = route.get('rule', 'CIRC-02')
        r = rules.get(rule_id) or rules.get('CIRC-02')
        if not r:
            continue
        pts = []
        missing = None
        for key in ('from', 'to'):
            ref = route.get(key)
            ep = by_id.get(ref)
            if ep:
                pts.append(endpoint_inset_point(ep))
            elif ref in all_by_id:
                o = all_by_id[ref]
                pts.append(bbox_center(o['bbox']) if o.get('bbox') else o['pos'])
            else:
                missing = ref
                break
        if missing is not None:
            findings.append(finding('SKIP', rule_id,
                f"route '{rid}' references unknown endpoint '{missing}'", []))
            continue
        routes_segments.append((rid, pts[0], pts[1]))
        if grid is None:
            continue
        width = corridor_width(grid, pts[0], pts[1])
        label = f"{route.get('from')}→{route.get('to')}"
        if width is None:
            findings.append(finding('ERROR', rule_id,
                f"{label} corridor blocked — no clear path on route '{rid}' "
                f"(min {r['min_cm']}cm)", [route.get('from'), route.get('to')]))
        elif width < r['min_cm']:
            findings.append(finding('ERROR', rule_id,
                f"{label} corridor {width:.0f}cm < {r['min_cm']}cm "
                f"(route '{rid}', ideal {r['ideal_cm']}cm)",
                [route.get('from'), route.get('to')]))
        elif width < r['ideal_cm']:
            findings.append(finding('WARN', rule_id,
                f"{label} corridor {width:.0f}cm below ideal {r['ideal_cm']}cm "
                f"(route '{rid}', min {r['min_cm']}cm)",
                [route.get('from'), route.get('to')]))
        else:
            findings.append(finding('PASS', rule_id,
                f"{label} corridor {width:.0f}cm (route '{rid}', "
                f"min {r['min_cm']}cm, ideal {r['ideal_cm']}cm)",
                [route.get('from'), route.get('to')]))
    return routes_segments

def check_zones(room, objects, rules, findings):
    """ZONE-01: zone bounds contain their members' bboxes (WARN beyond tolerance)."""
    tolerance = (rules.get('ZONE-01') or {}).get('tolerance_cm', 10)
    zones = room.get('zones') or []
    if not zones:
        findings.append(finding('SKIP', 'ZONE-01',
            "zones: not specified — run /planhaus:zone", []))
        return
    zone_by_id = {z['id']: z for z in zones if z.get('id')}
    for o in objects:
        if not o.get('zone') or not o.get('bbox'):
            continue
        zone = zone_by_id.get(o['zone'])
        if zone is None:
            findings.append(finding('SKIP', 'ZONE-01',
                f"{o['id']} references unknown zone '{o['zone']}'", [o['id']]))
            continue
        bounds = zone.get('bounds') or {}
        bx, by = bounds.get('x'), bounds.get('y')
        if not bx or not by:
            continue  # zone without numeric bounds
        minx, miny, maxx, maxy = bbox_aabb(o['bbox'])
        overflow = max(0, bx[0] - minx, maxx - bx[1], by[0] - miny, maxy - by[1])
        if overflow > tolerance:
            findings.append(finding('WARN', 'ZONE-01',
                f"{o['id']} extends {overflow:.0f}cm outside zone '{o['zone']}' bounds",
                [o['id']]))

def check_sightlines(room, objects, rules, findings):
    """SIGHT-01: focal point visible from each opening (tall items block)."""
    blocker_h = (rules.get('SIGHT-01') or {}).get('blocker_height_cm', 75)
    focal = room.get('focal_point') or {}
    ref = focal.get('ref')
    if not ref:
        findings.append(finding('SKIP', 'SIGHT-01',
            "focal_point: not specified — run /planhaus:zone", []))
        return
    target_obj = next((o for o in objects if o['id'] == ref), None)
    if target_obj is None:
        findings.append(finding('SKIP', 'SIGHT-01',
            f"focal_point ref '{ref}' not found in room", []))
        return
    target = bbox_center(target_obj['bbox']) if target_obj.get('bbox') else target_obj['pos']
    if target_obj['type'] in ('window', 'opening') and target_obj.get('width'):
        target = endpoint_inset_point(target_obj, inset=5)
    blockers = [o for o in floor_obstacles(objects) if o['id'] != ref]
    for op in objects:
        if op['type'] != 'opening':
            continue
        origin = endpoint_inset_point(op, inset=10)
        for o in blockers:
            if not segment_intersects_bbox(origin, target, o['bbox']):
                continue
            h = item_height(o)
            if h is None:
                findings.append(finding('SKIP', 'SIGHT-01',
                    f"height unknown on {o['id']} — cannot verify sightline "
                    f"from {op['id']} to '{ref}'", [o['id'], op['id']]))
            elif h > blocker_h:
                findings.append(finding('WARN', 'SIGHT-01',
                    f"focal point '{ref}' blocked from {op['id']} by {o['id']} "
                    f"(height {h}cm)", [op['id'], o['id'], ref]))

def run_checks(room, corners, objects, room_path):
    """Run the full rules engine. Returns findings sorted ERROR > WARN > SKIP."""
    rules = load_rules()
    findings = []
    if not rules:
        findings.append(finding('SKIP', 'RULES',
            f"rules table not found at {RULES_PATH}", []))
        return findings
    room_polygon = room_polygon_pts(room, corners)

    # Corridor grid (shared by CIRC-01 / CIRC-02)
    grid = None
    if room_polygon:
        doorway_segments = [endpoint_segment(e) for e in circulation_endpoints(objects)]
        grid = build_circulation_grid(room_polygon, floor_obstacles(objects),
                                      doorway_segments)

    routes_segments = check_circulation(room, objects, rules, findings, grid)
    check_seating(objects, rules, findings)
    check_dining(room, objects, rules, findings, room_polygon, routes_segments)
    check_bed(objects, rules, findings, room_polygon)
    check_kitchen(objects, rules, findings, room_polygon)
    check_heating(objects, rules, findings)
    check_doors(objects, rules, findings)
    check_windows(objects, rules, findings, room_polygon)
    check_tv(objects, rules, findings)
    check_proportions(room, corners, objects, rules, findings)
    check_rugs(room, corners, objects, rules, findings)
    check_pendants(objects, rules, findings)
    check_zones(room, objects, rules, findings)
    check_sightlines(room, objects, rules, findings)

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f['severity'], 3), f['rule']))
    return findings

def _json_safe(value):
    """Convert tuples to lists and trim floats for JSON output."""
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, float):
        return round(value, 1)
    return value

def serialize_object(obj):
    """Object dict for --json (drops internal wall vectors)."""
    skip = {'wall_unit', 'wall_perp'}
    return {k: _json_safe(v) for k, v in obj.items() if k not in skip}

def parse_args():
    parser = argparse.ArgumentParser(
        prog='room_spatial.py', add_help=False,
        description='Compute absolute positions from wall-relative room YAML.')
    parser.add_argument('room_yaml')
    parser.add_argument('--view', metavar='X,Y')
    parser.add_argument('--facing', metavar='DIR')
    parser.add_argument('--gap', nargs=2, metavar=('ID1', 'ID2'))
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--plot', nargs='?', const='', default=None, metavar='OUT.png')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json', action='store_true', dest='as_json')
    return parser.parse_args()

def main():
    global _JSON_MODE
    if len(sys.argv) < 2 or '-h' in sys.argv or '--help' in sys.argv:
        print(__doc__)
        sys.exit(0 if '--help' in sys.argv or '-h' in sys.argv else 1)

    args = parse_args()
    _JSON_MODE = args.as_json

    room_path = args.room_yaml
    room = load_room(room_path)
    corners = trace_corners(room['walls'])
    objects = get_objects(room, corners, room_path)

    # Validation + rules engine (rules only with --check)
    validation_warnings = validate_objects(objects, corners, room)
    findings = run_checks(room, corners, objects, room_path) if args.check else None
    # Under --check, geometry problems are first-class ERROR findings (GEOM-01)
    # so JSON consumers (e.g. the PostToolUse hook) see them in `rules` too.
    if findings is not None and validation_warnings:
        geom = [finding('ERROR', 'GEOM-01', w.replace('# WARNING: ', '', 1), [])
                for w in validation_warnings]
        findings = geom + findings
        findings.sort(key=lambda f: (SEVERITY_ORDER.get(f['severity'], 4), f['rule']))

    # Resolve --view / --gap inputs up-front (shared by text and JSON modes)
    viewer = None
    view_facing = None
    if args.view:
        coords = args.view.split(',')
        viewer = (int(coords[0]), int(coords[1]))
        if args.facing:
            view_facing = args.facing.lower()
            if view_facing not in FACING_ANGLES:
                print(f"Error: --facing must be north/south/east/west")
                sys.exit(1)

    gap_result = None
    if args.gap:
        id1, id2 = args.gap
        obj1 = next((o for o in objects if o['id'] == id1), None)
        obj2 = next((o for o in objects if o['id'] == id2), None)
        if not obj1:
            print(f"Error: '{id1}' not found", file=sys.stderr)
            sys.exit(1)
        if not obj2:
            print(f"Error: '{id2}' not found", file=sys.stderr)
            sys.exit(1)
        if not obj1.get('bbox') or not obj2.get('bbox'):
            print(f"Error: both items need bounding boxes (dimensions)", file=sys.stderr)
            sys.exit(1)
        gap_result = bbox_to_bbox_distance(obj1['bbox'], obj2['bbox'])

    if args.as_json:
        payload = {
            'room': room.get('name', room_path),
            'id': room.get('id'),
            'path': str(room_path),
            'units': 'cm',
            'origin': 'corner A (SW), X=East, Y=North',
            'corners': {name: [pos[0], pos[1]] for name, pos in sorted(corners.items())},
            'objects': [serialize_object(o) for o in objects],
            'warnings': validation_warnings,
        }
        if findings is not None:
            payload['rules'] = findings
        if gap_result is not None:
            payload['gap'] = {'items': [args.gap[0], args.gap[1]], 'cm': round(gap_result)}
        if args.plot is not None:
            viewer_info = None
            if viewer:
                visible = view_from(objects, corners, viewer, view_facing)
                viewer_info = {'pos': viewer, 'facing': view_facing, 'visible': visible}
            plot_room(room, corners, objects, room_path, viewer_info, args.plot or None)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if args.check:
            has_error = any(f['severity'] == 'ERROR' for f in findings)
            sys.exit(1 if has_error else 0)
        return

    print(f"# {room.get('name', room_path)}")
    print(f"# Origin (0,0) at corner A (SW)")
    print(f"# X = East, Y = North, units = cm\n")
    
    # Print corners
    print("## Corners")
    for name, pos in sorted(corners.items()):
        print(f"  {name}: ({pos[0]}, {pos[1]})")
    
    # Items with a clear "front" that face a direction
    DIRECTIONAL_KEYWORDS = ('sofa', 'chair', 'armchair', 'tv', 'desk', 'bed')
    
    # Print objects
    print("\n## Objects (absolute positions)")
    for obj in objects:
        pos = obj['pos']
        width_axis = obj.get('width_axis')
        facing = obj.get('facing')
        dims = obj.get('dims', {})
        obj_id = obj['id'].lower()
        
        if dims and (width_axis or facing):
            w = dims.get('width', dims.get('length', '?'))
            d = dims.get('depth', dims.get('length', '?'))
            
            # Use facing if explicitly set OR if directional item
            is_directional = any(kw in obj_id for kw in DIRECTIONAL_KEYWORDS)
            if facing and is_directional:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm facing {facing}")
            elif width_axis:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm ({width_axis})")
            else:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm")
        else:
            print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})")
    
    # Validation warnings (overlaps, out of bounds) - computed above
    if validation_warnings:
        print("\n## Validation Warnings")
        for warning in validation_warnings:
            print(warning)
    
    # Footprint summary (m²)
    items_with_dims = []
    for o in objects:
        if o['type'] in ('furniture', 'built_in') and o.get('dims'):
            dims = o['dims']
            w = dims.get('width', 0)
            d = dims.get('depth', 0)
            if w > 0 and d > 0:
                area_m2 = (w * d) / 10000  # cm² to m²
                items_with_dims.append((o['id'], area_m2))
    
    items_without_dims = [o['id'] for o in objects if o['type'] in ('furniture', 'built_in') and not (o.get('dims', {}).get('width') and o.get('dims', {}).get('depth'))]
    
    if items_with_dims or items_without_dims:
        print("\n## Footprint (m²)")
        total_area = 0
        for item_id, area in sorted(items_with_dims, key=lambda x: -x[1]):  # largest first
            print(f"  {area:5.2f}m² : {item_id}")
            total_area += area
        if items_with_dims:
            print(f"  ─────────")
            print(f"  {total_area:5.2f}m²   TOTAL ({len(items_with_dims)} items)")
        if items_without_dims:
            print(f"  (unknown): {', '.join(items_without_dims)}")

    # Rule check (--check)
    if findings is not None:
        print("\n## Rule check")
        for f in findings:
            print(f"  {f['severity']} {f['rule']}: {f['message']}")
        n_err = sum(1 for f in findings if f['severity'] == 'ERROR')
        n_warn = sum(1 for f in findings if f['severity'] == 'WARN')
        n_pass = sum(1 for f in findings if f['severity'] == 'PASS')
        n_skip = sum(1 for f in findings if f['severity'] == 'SKIP')
        if not findings:
            print("  All checks passed")
        print(f"  ── {n_err} error(s), {n_warn} warning(s), "
              f"{n_pass} passed, {n_skip} skipped")

    # View from position
    if viewer:
        if view_facing:
            print(f"\n## View from ({viewer[0]}, {viewer[1]}) facing {view_facing}")
        else:
            print(f"\n## View from ({viewer[0]}, {viewer[1]})")
        
        visible = view_from(objects, corners, viewer, view_facing)
        for obj in visible:
            print(f"  {obj['distance']:4}cm @ {obj['angle']:+4}° : {obj['id']}")
    
    # Edge-to-edge distance between two items
    if gap_result is not None:
        print(f"\n## Edge-to-edge gap")
        print(f"  {args.gap[0]} ↔ {args.gap[1]}: {round(gap_result)}cm")

    # Distance matrix
    if args.matrix:
        # Only items with bounding boxes (furniture, built-ins)
        items = [o for o in objects if o.get('bbox') and o['type'] in ('furniture', 'built_in')]
        
        if len(items) < 2:
            print("\n## Distance matrix: need at least 2 items with dimensions")
        else:
            print(f"\n## Edge-to-edge distances (cm)")
            
            # Object-to-object distances
            distances = []
            for i, obj1 in enumerate(items):
                for obj2 in items[i+1:]:
                    d = round(bbox_to_bbox_distance(obj1['bbox'], obj2['bbox']))
                    distances.append((d, obj1['id'], obj2['id']))
            
            # Object-to-wall distances
            walls = room.get('walls') or []
            for obj in items:
                for wall in walls:
                    wall_id = wall['id']
                    start, end = wall_id.split('-')
                    wall_start = corners[start]
                    wall_end = corners[end]
                    # Create wall as 2-point "bbox" and use segment distance
                    min_dist = float('inf')
                    for i in range(4):
                        p1, p2 = obj['bbox'][i], obj['bbox'][(i+1) % 4]
                        d = segment_to_segment_distance(p1, p2, wall_start, wall_end)
                        min_dist = min(min_dist, d)
                    distances.append((round(min_dist), obj['id'], f"wall:{wall_id}"))
            
            # Sort by distance and print
            distances.sort(key=lambda x: x[0])
            for d, id1, id2 in distances:
                print(f"  {d:4}cm : {id1} ↔ {id2}")
    
    # Plot floor plan
    if args.plot is not None:
        # Pass viewer info if specified
        viewer_info = None
        if viewer:
            visible = view_from(objects, corners, viewer, view_facing) if viewer else []
            viewer_info = {'pos': viewer, 'facing': view_facing, 'visible': visible}
        plot_room(room, corners, objects, room_path, viewer_info, args.plot or None)

    # Exit code: under --check, any ERROR finding (incl. GEOM-01) fails the run
    if args.check:
        has_error = any(f['severity'] == 'ERROR' for f in findings)
        sys.exit(1 if has_error else 0)

def plot_room(room, corners, objects, room_path, viewer_info=None, output_path=None):
    """Generate a floor plan image."""
    import math
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.patches import FancyArrow
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    # Colors
    COLORS = {
        'wall': '#2d3436',
        'furniture': '#74b9ff',
        'built_in': '#a29bfe',
        'light': '#fdcb6e',
        'window': '#00b894',
        'opening': '#e17055',
        'outlet': '#ff7675',
        'heating': '#d63031',
        'plumbing': '#0984e3',
    }
    
    # Draw room outline (walls)
    corner_list = []
    for wall in room['walls']:
        start = wall['id'].split('-')[0]
        corner_list.append(corners[start])
    corner_list.append(corner_list[0])  # close the polygon
    
    xs = [c[0] for c in corner_list]
    ys = [c[1] for c in corner_list]
    ax.plot(xs, ys, color=COLORS['wall'], linewidth=3, zorder=10)
    ax.fill(xs, ys, color='#f5f5f5', alpha=0.5, zorder=1)
    
    # Label corners
    for name, pos in corners.items():
        ax.annotate(name, (pos[0], pos[1]), fontsize=10, fontweight='bold',
                   ha='center', va='center', zorder=15,
                   bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))
    
    # Draw objects
    for obj in objects:
        pos = obj['pos']
        obj_type = obj['type']
        color = COLORS.get(obj_type, '#636e72')
        
        if obj.get('bbox'):
            # Draw bounding box
            bbox = obj['bbox']
            xs = [p[0] for p in bbox] + [bbox[0][0]]
            ys = [p[1] for p in bbox] + [bbox[0][1]]
            ax.fill(xs, ys, color=color, alpha=0.6, zorder=5)
            ax.plot(xs, ys, color=color, linewidth=1.5, zorder=6)
            
            # Label at center
            cx = sum(p[0] for p in bbox) / 4
            cy = sum(p[1] for p in bbox) / 4
            label = obj['id'].replace('-', '\n')
            ax.annotate(label, (cx, cy), fontsize=7, ha='center', va='center', zorder=7)
            
            # Draw facing arrow for directional items
            DIRECTIONAL = ('sofa', 'chair', 'armchair', 'tv', 'desk', 'bed')
            if obj.get('facing') and any(kw in obj['id'].lower() for kw in DIRECTIONAL):
                facing = obj['facing']
                arrow_len = 40
                dx, dy = {'north': (0, arrow_len), 'south': (0, -arrow_len),
                          'east': (arrow_len, 0), 'west': (-arrow_len, 0)}.get(facing, (0, 0))
                # Apply rotation if present
                rotation = obj.get('rotation', 0)
                if rotation:
                    rad = math.radians(-rotation)  # clockwise
                    dx_rot = dx * math.cos(rad) - dy * math.sin(rad)
                    dy_rot = dx * math.sin(rad) + dy * math.cos(rad)
                    dx, dy = dx_rot, dy_rot
                ax.annotate('', xy=(cx + dx, cy + dy), xytext=(cx, cy),
                           arrowprops=dict(arrowstyle='->', color='red', lw=2), zorder=8)
        else:
            # Skip types that are drawn separately below
            if obj_type in ('window', 'opening', 'outlet', 'heating', 'plumbing'):
                continue
            # Draw as point (lights and unlabeled built-ins)
            marker = 'o' if obj_type == 'light' else 's'
            ax.scatter([pos[0]], [pos[1]], c=color, s=80, marker=marker, zorder=5, edgecolors='black')
            ax.annotate(obj['id'], (pos[0], pos[1] + 20), fontsize=6, ha='center', zorder=6)
    
    # Draw windows and openings on walls
    for obj in objects:
        if obj['type'] == 'window':
            pos = obj['pos']
            width = obj.get('width', 100)
            unit = obj.get('wall_unit', (0, 1))
            # Draw along wall direction
            end_x = pos[0] + unit[0] * width
            end_y = pos[1] + unit[1] * width
            ax.plot([pos[0], end_x], [pos[1], end_y], 
                   color=COLORS['window'], linewidth=8, zorder=4, solid_capstyle='butt')
            # Label
            mid_x, mid_y = (pos[0] + end_x) / 2, (pos[1] + end_y) / 2
            ax.annotate(obj['id'], (mid_x, mid_y), fontsize=5, ha='center', va='bottom',
                       color=COLORS['window'], fontweight='bold', zorder=5)
        
        elif obj['type'] == 'opening':
            pos = obj['pos']
            width = obj.get('width', 100)
            unit = obj.get('wall_unit', (0, 1))
            end_x = pos[0] + unit[0] * width
            end_y = pos[1] + unit[1] * width
            # Draw as dashed line (gap in wall)
            linestyle = '-' if obj.get('has_door') else '--'
            ax.plot([pos[0], end_x], [pos[1], end_y], 
                   color=COLORS['opening'], linewidth=6, linestyle=linestyle, zorder=4)
            # Label with destination
            mid_x, mid_y = (pos[0] + end_x) / 2, (pos[1] + end_y) / 2
            label = f"→{obj.get('to', '')}" if obj.get('to') else obj['id']
            ax.annotate(label, (mid_x, mid_y), fontsize=5, ha='center', va='bottom',
                       color=COLORS['opening'], fontweight='bold', zorder=5)
        
        elif obj['type'] == 'outlet':
            pos = obj['pos']
            # Draw as small square
            ax.scatter([pos[0]], [pos[1]], c=COLORS['outlet'], s=60, marker='s', 
                      zorder=6, edgecolors='black', linewidths=0.5)
            ax.annotate(obj['id'], (pos[0], pos[1] + 15), fontsize=5, ha='center', 
                       color=COLORS['outlet'], zorder=7)
        
        elif obj['type'] == 'heating':
            pos = obj['pos']
            length = obj.get('length', 50)
            # Draw as thick red line
            ax.plot([pos[0], pos[0] + length], [pos[1], pos[1]], 
                   color=COLORS['heating'], linewidth=4, zorder=4)
            ax.annotate(obj['id'], (pos[0] + length/2, pos[1] + 15), fontsize=5, 
                       ha='center', color=COLORS['heating'], zorder=5)
        
        elif obj['type'] == 'plumbing':
            pos = obj['pos']
            # Draw as blue diamond
            ax.scatter([pos[0]], [pos[1]], c=COLORS['plumbing'], s=60, marker='D', 
                      zorder=6, edgecolors='black', linewidths=0.5)
            ax.annotate(obj['id'], (pos[0], pos[1] + 15), fontsize=5, ha='center', 
                       color=COLORS['plumbing'], zorder=7)
    
    # Draw viewer position and sight lines if specified
    if viewer_info:
        vpos = viewer_info['pos']
        facing_dir = viewer_info.get('facing')
        visible = viewer_info.get('visible', [])
        
        # Draw viewer marker (star)
        ax.scatter([vpos[0]], [vpos[1]], c='red', s=200, marker='*', zorder=20, edgecolors='black', linewidths=1)
        ax.annotate('VIEW', (vpos[0], vpos[1] - 40), fontsize=8, ha='center', 
                   fontweight='bold', color='red', zorder=21)
        
        # Draw facing cone if specified
        if facing_dir:
            cone_len = 150
            dir_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
            if facing_dir in dir_map:
                dx, dy = dir_map[facing_dir]
                # Draw cone edges (45° each side)
                import math
                for angle_offset in [-45, 45]:
                    rad = math.radians(angle_offset)
                    rx = dx * math.cos(rad) - dy * math.sin(rad)
                    ry = dx * math.sin(rad) + dy * math.cos(rad)
                    ax.plot([vpos[0], vpos[0] + rx * cone_len], 
                           [vpos[1], vpos[1] + ry * cone_len],
                           color='red', linestyle='--', alpha=0.5, linewidth=1, zorder=15)
        
        # Draw distance lines to visible objects
        for obj in visible:
            obj_pos = obj['pos']
            dist = obj['distance']
            # Draw line
            ax.plot([vpos[0], obj_pos[0]], [vpos[1], obj_pos[1]], 
                   color='red', linestyle=':', alpha=0.4, linewidth=1, zorder=3)
            # Label with distance at midpoint
            mid_x = (vpos[0] + obj_pos[0]) / 2
            mid_y = (vpos[1] + obj_pos[1]) / 2
            ax.annotate(f'{dist}cm', (mid_x, mid_y), fontsize=6, ha='center', 
                       color='red', alpha=0.8, zorder=4,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
    
    ax.set_aspect('equal')
    ax.set_xlabel('X (East) - cm')
    ax.set_ylabel('Y (North) - cm')
    ax.set_title(room.get('name', 'Room Layout'))
    ax.grid(True, alpha=0.3)
    
    # Add legend
    legend_elements = [
        patches.Patch(facecolor=COLORS['furniture'], label='Furniture'),
        patches.Patch(facecolor=COLORS['built_in'], label='Built-in'),
        patches.Patch(facecolor=COLORS['window'], label='Window'),
        patches.Patch(facecolor=COLORS['opening'], label='Opening'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['light'], 
                   markersize=10, label='Light'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=COLORS['outlet'], 
                   markersize=8, label='Outlet'),
    ]
    if viewer_info:
        legend_elements.append(plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='red',
                                          markersize=12, label='Viewpoint'))
    ax.legend(handles=legend_elements, loc='upper left', fontsize=8)
    
    # Determine output path
    if not output_path:
        output_path = str(Path(room_path).with_suffix('.png'))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    note(f"\n## Floor plan saved to: {output_path}")

if __name__ == '__main__':
    main()

