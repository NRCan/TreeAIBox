"""
Diagnostic tool to check coordinate systems of LAS files and shapefiles.
Helps identify mismatches that cause PolyClipData failures.
"""

import os
import sys
import laspy
import shapefile

def check_las_projection(las_file):
    """Extract projection information from LAS file."""
    print(f"\n{'='*60}")
    print(f"LAS File: {las_file}")
    print(f"{'='*60}")
    
    if not os.path.exists(las_file):
        print(f"[ERROR] LAS file not found: {las_file}")
        return None
    
    try:
        with laspy.open(las_file) as f:
            header = f.header
            
            # Check for VLR records containing projection info
            vlr_records = header.vlrs
            
            has_proj = False
            for vlr in vlr_records:
                if hasattr(vlr, 'record_id'):
                    print(f"  VLR Record ID: {vlr.record_id}")
                    if hasattr(vlr, 'description'):
                        print(f"  Description: {vlr.description}")
                    has_proj = True
            
            if not has_proj:
                print("  [WARNING] No projection information found in VLR records")
            
            # Show header info
            print(f"\n  Points: {header.point_count}")
            print(f"  Min X: {header.mins[0]:.2f}")
            print(f"  Max X: {header.maxs[0]:.2f}")
            print(f"  Min Y: {header.mins[1]:.2f}")
            print(f"  Max Y: {header.maxs[1]:.2f}")
            print(f"  Min Z: {header.mins[2]:.2f}")
            print(f"  Max Z: {header.maxs[2]:.2f}")
            
            # Check for GeoKeyDirectoryTag
            for vlr in vlr_records:
                if hasattr(vlr, 'record_id') and vlr.record_id == 34735:
                    print(f"\n  [INFO] Found GeoKeyDirectoryTag (EPSG code may be embedded)")
            
            return header
            
    except Exception as e:
        print(f"[ERROR] Could not read LAS file: {e}")
        return None

def check_shapefile_projection(shp_folder):
    """Check shapefile projection from .prj file."""
    print(f"\n{'='*60}")
    print(f"Shapefile Folder: {shp_folder}")
    print(f"{'='*60}")
    
    shp_files = [f for f in os.listdir(shp_folder) if f.endswith('.shp')]
    if not shp_files:
        print("[ERROR] No .shp files found in folder")
        return None
    
    shp_file = os.path.join(shp_folder, shp_files[0])
    shp_base = os.path.splitext(shp_file)[0]
    
    print(f"  Shapefile: {shp_files[0]}")
    
    # Check for .prj file
    prj_file = shp_base + '.prj'
    if os.path.exists(prj_file):
        with open(prj_file, 'r') as f:
            prj_content = f.read().strip()
        print(f"  Projection (.prj): {prj_content}")
    else:
        print("  [WARNING] No .prj file found - no defined coordinate system")
    
    # Read shapefile metadata
    try:
        sf = shapefile.Reader(shp_file)
        print(f"  Records: {sf.numRecords}")
        print(f"  Shape Type: {sf.shapeType} ({get_shape_type_name(sf.shapeType)})")
        
        if sf.numRecords > 0:
            first_shape = sf.shape(0)
            if hasattr(first_shape, 'bbox'):
                bbox = first_shape.bbox
                print(f"  First polygon bbox: ({bbox[0]:.2f}, {bbox[1]:.2f}) to ({bbox[2]:.2f}, {bbox[3]:.2f})")
        
        return sf
        
    except Exception as e:
        print(f"[ERROR] Could not read shapefile: {e}")
        return None

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

def main():
    print("Coordinate System Diagnostic Tool")
    print("=" * 60)
    
    if len(sys.argv) < 3:
        print("\nUsage: python check_coordinate_system.py <las_file> <shapefile_folder>")
        print("\nExample:")
        print('  python check_coordinate_system.py "D:/Data/file.las" "D:/Data/shapefiles/"')
        sys.exit(1)
    
    las_file = sys.argv[1]
    shp_folder = sys.argv[2]
    
    # Check LAS file
    las_header = check_las_projection(las_file)
    
    # Check shapefile
    sf = check_shapefile_projection(shp_folder)
    
    print(f"\n{'='*60}")
    print("DIAGNOSIS")
    print(f"{'='*60}")
    
    if las_header and sf:
        print("\n[RECOMMENDATION]")
        print("If PolyClipData fails with 'Problems with polygon overlay':")
        print("1. Ensure both files use the same coordinate system")
        print("2. If shapefile has no .prj file, define its projection")
        print("3. Use QGIS or ArcGIS to reproject one file to match the other")
        print("4. Common projections for LiDAR: UTM zones, NAD83 / WGS84")
    else:
        print("\n[ERROR] Could not complete diagnosis - check file paths and permissions")

if __name__ == '__main__':
    main()
