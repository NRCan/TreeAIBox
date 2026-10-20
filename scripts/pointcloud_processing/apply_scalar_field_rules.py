"""
Apply rules to modify scalar field values in LAS/LAZ files
Example: Ensure stem points (stemcls=2) are not labeled as branches (branchcls=2)
"""

import laspy
import numpy as np
import os
import sys
from tkinter import Tk, filedialog


def apply_stemcls_branchcls_rule(las_data):
    """
    Apply rule: Points where stemcls=2 should not have branchcls=2
    Sets branchcls to 1 for all points where stemcls=2
    (Value 1 = non-branch points, Value 2 = branch points)
    """
    # Check if required fields exist
    if 'stemcls' not in las_data.point_format.dimension_names:
        print("Error: 'stemcls' field not found in the point cloud")
        return False
    
    if 'branchcls' not in las_data.point_format.dimension_names:
        print("Error: 'branchcls' field not found in the point cloud")
        return False
    
    # Get the fields
    stemcls = las_data['stemcls']
    branchcls = las_data['branchcls']
    
    # Count points before modification
    stem_points = np.sum(stemcls == 2)
    branch_points_before = np.sum(branchcls == 2)
    conflicts_before = np.sum((stemcls == 2) & (branchcls == 2))
    
    print(f"\nBefore applying rule:")
    print(f"  Points with stemcls=2 (stem): {stem_points:,}")
    print(f"  Points with branchcls=2 (branch): {branch_points_before:,}")
    print(f"  Conflicts (both stemcls=2 AND branchcls=2): {conflicts_before:,}")
    
    if conflicts_before == 0:
        print("\nNo conflicts found - no changes needed!")
        return False
    
    # Apply the rule: where stemcls=2, set branchcls to 1 (non-branch)
    mask = stemcls == 2
    las_data['branchcls'][mask] = 1
    
    # Count after modification
    branch_points_after = np.sum(las_data['branchcls'] == 2)
    conflicts_after = np.sum((las_data['stemcls'] == 2) & (las_data['branchcls'] == 2))
    
    print(f"\nAfter applying rule:")
    print(f"  Points with stemcls=2 (stem): {stem_points:,} (unchanged)")
    print(f"  Points with branchcls=2 (branch): {branch_points_after:,} (was {branch_points_before:,})")
    print(f"  Points with branchcls=1 (non-branch): {np.sum(las_data['branchcls'] == 1):,}")
    print(f"  Conflicts: {conflicts_after:,} (was {conflicts_before:,})")
    print(f"  Points modified: {conflicts_before:,}")
    
    return True


def apply_custom_rule(las_data, source_field, source_value, target_field, new_value):
    """
    Apply a custom rule: Where source_field=source_value, set target_field=new_value
    
    Args:
        las_data: laspy LasData object
        source_field: Name of the field to check (e.g., 'stemcls')
        source_value: Value to match in source field (e.g., 2)
        target_field: Name of the field to modify (e.g., 'branchcls')
        new_value: New value to set in target field (e.g., 0)
    """
    # Check if fields exist
    if source_field not in las_data.point_format.dimension_names:
        print(f"Error: '{source_field}' field not found in the point cloud")
        return False
    
    if target_field not in las_data.point_format.dimension_names:
        print(f"Error: '{target_field}' field not found in the point cloud")
        return False
    
    # Get the fields
    source_data = las_data[source_field]
    target_data = las_data[target_field]
    
    # Count points before modification
    matches = np.sum(source_data == source_value)
    target_matches_before = np.sum(target_data == new_value)
    affected = np.sum((source_data == source_value) & (target_data != new_value))
    
    print(f"\nBefore applying rule:")
    print(f"  Points with {source_field}={source_value}: {matches:,}")
    print(f"  Points with {target_field}={new_value}: {target_matches_before:,}")
    print(f"  Points that will be modified: {affected:,}")
    
    if affected == 0:
        print("\nNo points need modification!")
        return False
    
    # Apply the rule
    mask = source_data == source_value
    las_data[target_field][mask] = new_value
    
    # Count after modification
    target_matches_after = np.sum(las_data[target_field] == new_value)
    
    print(f"\nAfter applying rule:")
    print(f"  Points with {target_field}={new_value}: {target_matches_after:,} (was {target_matches_before:,})")
    print(f"  Points modified: {affected:,}")
    
    return True


def select_file():
    """Open a file dialog to select a LAS/LAZ file"""
    root = Tk()
    root.withdraw()  # Hide the main window
    root.attributes('-topmost', True)  # Bring dialog to front
    
    file_path = filedialog.askopenfilename(
        title="Select LAS/LAZ file",
        filetypes=[
            ("LAS/LAZ files", "*.las *.laz"),
            ("LAS files", "*.las"),
            ("LAZ files", "*.laz"),
            ("All files", "*.*")
        ],
        initialdir=os.path.expanduser("~")
    )
    
    root.destroy()
    return file_path


def main():
    # Get input file
    if len(sys.argv) > 1:
        input_file = sys.argv[1].strip('"').strip("'")  # Remove quotes if present
    else:
        print("\nOpening file browser...")
        input_file = select_file()
        
        if not input_file:
            print("No file selected. Exiting.")
            return
        
        print(f"Selected: {input_file}")
    
    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        print("\nTip: If passing path as argument, don't include quotes")
        return
    
    # Load the point cloud
    print(f"\nLoading point cloud: {input_file}")
    las = laspy.read(input_file)
    total_points = len(las.points)
    print(f"Total points: {total_points:,}")
    
    # Show available scalar fields
    print(f"\nAvailable scalar fields:")
    for i, field in enumerate(las.point_format.dimension_names, 1):
        if field.lower() not in ['x', 'y', 'z', 'intensity', 'return_number', 'number_of_returns', 
                                   'scan_direction_flag', 'edge_of_flight_line', 'classification',
                                   'synthetic', 'key_point', 'withheld', 'scan_angle_rank', 
                                   'user_data', 'point_source_id', 'gps_time', 'red', 'green', 'blue']:
            values = las[field]
            unique_vals = np.unique(values)
            print(f"  {i}. {field}: {len(unique_vals)} unique values - {unique_vals[:10]}" + 
                  ("..." if len(unique_vals) > 10 else ""))
    
    # Ask which rule to apply
    print("\n" + "="*60)
    print("Rule Options:")
    print("="*60)
    print("1. Apply stemcls/branchcls rule (stemcls=2 → branchcls=1)")
    print("   Ensures stem points are marked as non-branch")
    print("2. Apply custom rule (specify fields and values)")
    print("="*60)
    
    choice = input("\nSelect rule option (1 or 2): ").strip()
    
    modified = False
    
    if choice == '1':
        # Apply the predefined stemcls/branchcls rule
        modified = apply_stemcls_branchcls_rule(las)
    
    elif choice == '2':
        # Custom rule
        print("\nCustom Rule: IF <source_field> = <source_value> THEN SET <target_field> = <new_value>")
        print("Example: IF stemcls = 2 THEN SET branchcls = 0")
        
        source_field = input("\nEnter source field name (e.g., stemcls): ").strip()
        source_value = float(input(f"Enter value to match in {source_field} (e.g., 2): ").strip())
        target_field = input("Enter target field to modify (e.g., branchcls): ").strip()
        new_value = float(input(f"Enter new value to set in {target_field} (e.g., 0): ").strip())
        
        modified = apply_custom_rule(las, source_field, source_value, target_field, new_value)
    
    else:
        print("Invalid choice!")
        return
    
    # Save the modified file
    if modified:
        print("\n" + "="*60)
        save = input("\nSave modified point cloud? (y/n): ").strip().lower()
        
        if save == 'y':
            # Generate output filename
            base, ext = os.path.splitext(input_file)
            output_file = f"{base}_rules_applied{ext}"
            
            # Ask if user wants custom output path
            custom = input(f"Save as '{output_file}'? (y/n, n to specify custom path): ").strip().lower()
            if custom == 'n':
                output_file = input("Enter output file path: ").strip()
            
            # Save
            print(f"\nSaving to: {output_file}")
            las.write(output_file)
            print(f"✓ Saved successfully!")
            print(f"  Output: {output_file}")
            print(f"  Total points: {total_points:,}")
        else:
            print("\nChanges discarded - file not saved.")
    else:
        print("\nNo changes made to the file.")


if __name__ == "__main__":
    main()
