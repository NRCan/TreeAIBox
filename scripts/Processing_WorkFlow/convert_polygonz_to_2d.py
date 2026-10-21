"""
Convert PolygonZ (3D) shapefile to Polygon (2D) shapefile.
This can fix PolyClipData compatibility issues with 3D polygons.
"""

import shapefile
import os
import sys

def convert_polygonz_to_polygon(input_shp, output_shp=None):
    """
    Convert a PolygonZ shapefile to a regular 2D Polygon shapefile.
    
    Args:
        input_shp: Path to input .shp file (PolygonZ)
        output_shp: Path to output .shp file (Polygon). If None, appends '_2D' to input name.
    """
    
    if output_shp is None:
        base = os.path.splitext(input_shp)[0]
        output_shp = base + '_2D.shp'
    
    print(f"Converting: {input_shp}")
    print(f"Output: {output_shp}")
    
    # Read input shapefile
    reader = shapefile.Reader(input_shp)
    
    print(f"Input shape type: {reader.shapeType} ({get_shape_type_name(reader.shapeType)})")
    print(f"Number of records: {reader.numRecords}")
    
    # Create writer for 2D polygon
    writer = shapefile.Writer(output_shp, shapeType=shapefile.POLYGON)
    
    # Copy fields
    for field in reader.fields[1:]:  # Skip DeletionFlag
        writer.field(*field)
    
    # Convert each record
    for i in range(reader.numRecords):
        shape = reader.shape(i)
        record = reader.record(i)
        
        # Extract 2D points (ignore Z values)
        points_2d = [(x, y) for x, y, *rest in shape.points]
        
        # Get parts information
        parts = list(shape.parts) if hasattr(shape, 'parts') else [0]
        
        # Add the 2D polygon using correct pyshp API
        writer.poly([points_2d])
        writer.record(*record)
        
        if (i + 1) % 10 == 0 or i == reader.numRecords - 1:
            print(f"  Processed {i + 1}/{reader.numRecords} polygons")
    
    writer.close()
    
    # Copy projection file if it exists
    input_prj = os.path.splitext(input_shp)[0] + '.prj'
    output_prj = os.path.splitext(output_shp)[0] + '.prj'
    if os.path.exists(input_prj):
        import shutil
        shutil.copy2(input_prj, output_prj)
        print(f"Copied projection file: {os.path.basename(output_prj)}")
    
    print(f"\nConversion complete!")
    print(f"Output shapefile: {output_shp}")
    
    # Verify output
    verify_reader = shapefile.Reader(output_shp)
    print(f"Output shape type: {verify_reader.shapeType} ({get_shape_type_name(verify_reader.shapeType)})")
    print(f"Output records: {verify_reader.numRecords}")
    
    return output_shp

def get_shape_type_name(shape_type):
    """Get human-readable name for shapefile shape type."""
    shape_types = {
        0: "Null Shape",
        1: "Point",
        3: "PolyLine",
        5: "Polygon",
        8: "MultiPoint",
        11: "PointZ",
        13: "PolyLineZ",
        15: "PolygonZ",
        18: "MultiPointZ",
        21: "PointM",
        23: "PolyLineM",
        25: "PolygonM",
        28: "MultiPointM",
        31: "MultiPatch"
    }
    return shape_types.get(shape_type, f"Unknown ({shape_type})")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python convert_polygonz_to_2d.py <input.shp> [output.shp]")
        print("\nExample:")
        print('  python convert_polygonz_to_2d.py "D:/Data/polygons.shp"')
        print('  python convert_polygonz_to_2d.py "D:/Data/polygons.shp" "D:/Data/polygons_2D.shp"')
        sys.exit(1)
    
    input_shp = sys.argv[1]
    output_shp = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(input_shp):
        print(f"[ERROR] Input file not found: {input_shp}")
        sys.exit(1)
    
    convert_polygonz_to_polygon(input_shp, output_shp)
