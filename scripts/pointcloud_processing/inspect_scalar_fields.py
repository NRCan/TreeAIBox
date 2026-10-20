"""
Quick diagnostic script to inspect scalar field values in a LAS file
"""

import laspy
import numpy as np
import sys
from tkinter import Tk, filedialog


def select_file():
    """Open a file dialog to select a LAS/LAZ file"""
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    file_path = filedialog.askopenfilename(
        title="Select LAS/LAZ file to inspect",
        filetypes=[
            ("LAS/LAZ files", "*.las *.laz"),
            ("All files", "*.*")
        ]
    )
    
    root.destroy()
    return file_path


def main():
    if len(sys.argv) > 1:
        input_file = sys.argv[1].strip('"').strip("'")
    else:
        print("\nOpening file browser...")
        input_file = select_file()
        
        if not input_file:
            print("No file selected. Exiting.")
            return
    
    print(f"\n{'='*70}")
    print(f"Inspecting: {input_file}")
    print(f"{'='*70}")
    
    las = laspy.read(input_file)
    total_points = len(las.points)
    print(f"\nTotal points: {total_points:,}")
    
    print(f"\n{'='*70}")
    print("SCALAR FIELD ANALYSIS:")
    print(f"{'='*70}")
    
    for field in las.point_format.dimension_names:
        if field.lower() not in ['x', 'y', 'z', 'intensity', 'return_number', 'number_of_returns']:
            values = las[field]
            unique_vals = np.unique(values)
            
            print(f"\n{field}:")
            print(f"  Unique values: {unique_vals}")
            print(f"  Value distribution:")
            
            for val in unique_vals:
                count = np.sum(values == val)
                percentage = (count / total_points) * 100
                print(f"    {val}: {count:,} points ({percentage:.2f}%)")
    
    # Special check for stemcls and branchcls
    if 'stemcls' in las.point_format.dimension_names and 'branchcls' in las.point_format.dimension_names:
        stemcls = las['stemcls']
        branchcls = las['branchcls']
        
        print(f"\n{'='*70}")
        print("CONFLICT ANALYSIS:")
        print(f"{'='*70}")
        
        stem_points = np.sum(stemcls == 2)
        branch_points = np.sum(branchcls == 2)
        conflicts = np.sum((stemcls == 2) & (branchcls == 2))
        stem_as_nonbranch = np.sum((stemcls == 2) & (branchcls == 1))
        
        print(f"\nStem points (stemcls=2): {stem_points:,}")
        print(f"Branch points (branchcls=2): {branch_points:,}")
        print(f"Conflicts (stemcls=2 AND branchcls=2): {conflicts:,}")
        print(f"Correctly marked (stemcls=2 AND branchcls=1): {stem_as_nonbranch:,}")
        
        if conflicts > 0:
            print(f"\n⚠ WARNING: {conflicts:,} points are marked as BOTH stem AND branch!")
        else:
            print(f"\n✓ No conflicts found")


if __name__ == "__main__":
    main()
