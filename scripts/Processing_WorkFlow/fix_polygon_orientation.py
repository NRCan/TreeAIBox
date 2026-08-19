"""
Fix polygon orientation/winding order for shapefiles.
PolyClipData can be sensitive to polygon vertex order.
"""

import shapefile
import os
import sys

def signed_area(points):
    """Calculate signed area of a polygon (positive = counter-clockwise)."""
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return area / 2.0

def ensure_clockwise(points):
    """Ensure polygon vertices are in clockwise order."""
    if signed_area(points) > 0:  # counter-clockwise
        return points[::-1]  # reverse
    return points

def ensure_counter_clockwise(points):
    """Ensure polygon vertices are in counter-clockwise order."""
    if signed_area(points) < 0:  # clockwise
        return points[::-1]  # reverse
    return points

def fix_polygon_orientation(input_shp, output_shp=None, orientation='clockwise'):
    """
    Fix polygon orientation in a shapefile.
    
    Args:
        input_shp: Path to input shapefile
        output_shp: Path to output shapefile. If None, appends '_oriented' to input name.
        orientation: 'clockwise' or 'counter_clockwise'
    """
    
    if output_shp is None:
        base = os.path.splitext(input_shp)[0]
        output_shp = base + '_oriented.shp'
    
    print(f"Fixing orientation: {input_shp}")
    print(f"Output: {output_shp}")
    
    reader = shapefile.Reader(input_shp)
    print(f"Input shape type: {reader.shapeType}")
    print(f"Number of records: {reader.numRecords}")
    
    # Determine output shape type
    if reader.shapeType in [5, 15]:  # Polygon or PolygonZ
        output_shape_type = shapefile.POLYGON
    else:
        print(f"[ERROR] Unsupported shape type: {reader.shapeType}")
        return None
    
    writer = shapefile.Writer(output_shp, shapeType=output_shape_type)
    
    # Copy fields
    for field in reader.fields[1:]:
        writer.field(*field)
    
    orient_func = ensure_clockwise if orientation == 'clockwise' else ensure_counter_clockwise
    
    for i in range(reader.numRecords):
        shape = reader.shape(i)
        record = reader.record(i)
        
        # Get points and parts
        points = list(shape.points)
        parts = list(shape.parts) if hasattr(shape, 'parts') and shape.parts is not None else [0]
        parts.append(len(points))  # Add end marker
        
        oriented_polygons = []
        for j in range(len(parts) - 1):
            ring_points = points[parts[j]:parts[j+1]]
            if len(ring_points) > 0:
                # For shapefile polygons, outer ring should be clockwise
                oriented = orient_func(ring_points)
                oriented_polygons.append(oriented)
        
        if oriented_polygons:
            writer.poly(oriented_polygons)
            writer.record(*record)
        
        print(f"  Processed {i + 1}/{reader.numRecords} polygons")
    
    writer.close()
    
    # Copy projection file
    input_prj = os.path.splitext(input_shp)[0] + '.prj'
    output_prj = os.path.splitext(output_shp)[0] + '.prj'
    if os.path.exists(input_prj):
        import shutil
        shutil.copy2(input_prj, output_prj)
        print(f"Copied projection file: {os.path.basename(output_prj)}")
    
    print(f"\nOrientation fix complete!")
    
    # Verify
    verify_reader = shapefile.Reader(output_shp)
    print(f"Output shape type: {verify_reader.shapeType}")
    print(f"Output records: {verify_reader.numRecords}")
    
    return output_shp

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python fix_polygon_orientation.py <input.shp> [output.shp] [orientation]")
        print("\nExample:")
        print('  python fix_polygon_orientation.py "D:/Data/polygons.shp"')
        print('  python fix_polygon_orientation.py "D:/Data/polygons.shp" "D:/Data/polygons_fixed.shp" clockwise')
        print('  python fix_polygon_orientation.py "D:/Data/polygons.shp" "D:/Data/polygons_ccw.shp" counter_clockwise')
        sys.exit(1)
    
    input_shp = sys.argv[1]
    output_shp = sys.argv[2] if len(sys.argv) > 2 else None
    orientation = sys.argv[3] if len(sys.argv) > 3 else 'clockwise'
    
    if not os.path.exists(input_shp):
        print(f"[ERROR] Input file not found: {input_shp}")
        sys.exit(1)
    
    fix_polygon_orientation(input_shp, output_shp, orientation)
