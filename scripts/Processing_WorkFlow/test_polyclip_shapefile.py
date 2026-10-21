"""
Test script to diagnose PolyClipData shapefile issues.
Tests different command variations to identify the exact problem.
"""

import subprocess
import os

def test_polyclipdata(fusion_exe, shp_file, las_file, output_file):
    """Run various PolyClipData tests to diagnose the issue."""
    
    print("="*60)
    print("PolyClipData Diagnostic Tests")
    print("="*60)
    
    # Test 1: Basic clip without /shape parameter (clip all polygons)
    print("\n[Test 1] Basic clip (all polygons, no /shape filter)")
    cmd1 = [fusion_exe, '/verbose', shp_file, output_file.replace('.las', '_test1.las'), las_file]
    print(f"Command: {' '.join(cmd1)}")
    result1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=60)
    print(f"Exit code: {result1.returncode}")
    if result1.stdout:
        print(f"Output:\n{result1.stdout.strip()}")
    if result1.stderr:
        print(f"Error:\n{result1.stderr.strip()}")
    
    # Test 2: Using /shape with wildcard
    print("\n[Test 2] Using /shape with wildcard (/shape:1,*)")
    cmd2 = [fusion_exe, '/verbose', '/shape:1,*', shp_file, output_file.replace('.las', '_test2.las'), las_file]
    print(f"Command: {' '.join(cmd2)}")
    result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
    print(f"Exit code: {result2.returncode}")
    if result2.stdout:
        print(f"Output:\n{result2.stdout.strip()}")
    if result2.stderr:
        print(f"Error:\n{result2.stderr.strip()}")
    
    # Test 3: Using /shape with specific value
    print("\n[Test 3] Using /shape with specific value (/shape:1,101.378972792)")
    cmd3 = [fusion_exe, '/verbose', '/shape:1,101.378972792', shp_file, output_file.replace('.las', '_test3.las'), las_file]
    print(f"Command: {' '.join(cmd3)}")
    result3 = subprocess.run(cmd3, capture_output=True, text=True, timeout=60)
    print(f"Exit code: {result3.returncode}")
    if result3.stdout:
        print(f"Output:\n{result3.stdout.strip()}")
    if result3.stderr:
        print(f"Error:\n{result3.stderr.strip()}")
    
    # Test 4: Try with forward slashes only
    print("\n[Test 4] Using forward slashes in paths")
    shp_fwd = shp_file.replace('\\', '/')
    las_fwd = las_file.replace('\\', '/')
    out_fwd = output_file.replace('.las', '_test4.las').replace('\\', '/')
    cmd4 = [fusion_exe, '/verbose', '/shape:1,101.378972792', shp_fwd, out_fwd, las_fwd]
    print(f"Command: {' '.join(cmd4)}")
    result4 = subprocess.run(cmd4, capture_output=True, text=True, timeout=60)
    print(f"Exit code: {result4.returncode}")
    if result4.stdout:
        print(f"Output:\n{result4.stdout.strip()}")
    if result4.stderr:
        print(f"Error:\n{result4.stderr.strip()}")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    tests = [
        ("Basic clip (no filter)", result1.returncode),
        ("Wildcard /shape:1,*", result2.returncode),
        ("Specific value /shape:1,101.378972792", result3.returncode),
        ("Forward slashes only", result4.returncode),
    ]
    
    for name, code in tests:
        status = "✓ PASS" if code == 0 else "✗ FAIL"
        print(f"{status} - {name} (exit code: {code})")

if __name__ == '__main__':
    fusion_exe = r"D:\Enhanced Forest Inventory\Fusion\PolyClipData.exe"
    shp_file = r"D:\Enhanced Forest Inventory\Data\New DataStore\ClipPolygon\Transect Ploygon\ClipPolygonTransect.shp"
    las_file = r"D:\Enhanced Forest Inventory\Data\New DataStore\2025\LeafOFF\20250407_LLR_L2_AllPoints_Orthometric_crownoff.las"
    output_file = r"D:\Enhanced Forest Inventory\Data\New DataStore\ClipPolygon\Transect Ploygon\clipped_to_polygon\diagnostic_test.las"
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    test_polyclipdata(fusion_exe, shp_file, las_file, output_file)
