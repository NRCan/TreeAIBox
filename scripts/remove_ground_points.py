"""
Remove ground points from point cloud
Removes points that match specific ground classification values
"""
import os
import sys
import laspy
import numpy as np
from tkinter import Tk, filedialog


def select_file():
    """Open a file dialog to select a LAS/LAZ file"""
    root = Tk()
    root.withdraw()  # Hide the main window
    root.attributes('-topmost', True)  # Bring dialog to front
    
    file_path = filedialog.askopenfilename(
        title="Select LAS/LAZ file to remove ground points",
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


def list_scalar_fields(las):
    """List all available scalar fields in the LAS file"""
    fields = []
    
    # Get standard dimensions
    for dim_name in las.point_format.dimension_names:
        fields.append(dim_name)
    
    # Get extra dimensions
    for extra_dim in las.point_format.extra_dimension_names:
        fields.append(extra_dim)
    
    return fields


def get_scalar_field_data(las, field_name):
    """Get data from a scalar field"""
    try:
        return np.array(getattr(las, field_name))
    except AttributeError:
        print(f"Error: Field '{field_name}' not found")
        return None


def remove_ground_points(las, field_name, ground_values):
    """Remove ground points based on scalar field values"""
    field_data = get_scalar_field_data(las, field_name)
    if field_data is None:
        return None
    
    # Create boolean mask for points NOT matching ground values (keep non-ground)
    mask = ~np.isin(field_data, ground_values)
    
    # Get unique values in the field for statistics
    unique_values = np.unique(field_data)
    print(f"\nAvailable values in '{field_name}': {unique_values}")
    print(f"Total points: {len(las.points)}")
    print(f"Ground points (to be removed): {np.sum(~mask)}")
    print(f"Non-ground points (to be kept): {np.sum(mask)}")
    
    return mask


def save_filtered_points(las, mask, output_path):
    """Save filtered points to a new LAS file"""
    # Create a new LAS file with the filtered points
    filtered_las = laspy.LasData(las.header)
    filtered_las.points = las.points[mask]
    
    # Write to file
    filtered_las.write(output_path)
    print(f"\nGround-removed point cloud saved to: {output_path}")


def main():
    # Get input file path
    if len(sys.argv) > 1:
        input_file = sys.argv[1].strip('"').strip("'")
    else:
        print("\nOpening file browser...")
        input_file = select_file()
        
        if not input_file:
            print("No file selected. Exiting.")
            return
        
        print(f"Selected: {input_file}")
    
    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        return
    
    print(f"\nLoading point cloud: {input_file}")
    las = laspy.read(input_file)
    print(f"Loaded {len(las.points)} points")
    
    # List available scalar fields
    fields = list_scalar_fields(las)
    print("\n" + "="*60)
    print("Available Scalar Fields (for ground classification):")
    print("="*60)
    for i, field in enumerate(fields, 1):
        try:
            data = get_scalar_field_data(las, field)
            if data is not None:
                unique_vals = np.unique(data)
                print(f"{i:2d}. {field:20s} - Range: [{np.min(data):.2f}, {np.max(data):.2f}], Unique values: {len(unique_vals)}")
                if len(unique_vals) <= 20:  # Show values if not too many
                    print(f"     Values: {unique_vals}")
        except:
            print(f"{i:2d}. {field:20s} - (unable to read)")
    print("="*60)
    
    # Suggest common ground field names
    common_ground_fields = ['classification', 'class', 'Classification', 'ground', 'Ground']
    suggested_field = None
    for common_field in common_ground_fields:
        if common_field in fields:
            suggested_field = common_field
            break
    
    if suggested_field:
        print(f"\nSuggested field: '{suggested_field}' (commonly used for ground classification)")
    
    # Ask user to select a field
    while True:
        try:
            selection = input("\nEnter the number or name of the scalar field for ground classification: ").strip()
            
            # Check if it's a number (index) or name
            if selection.isdigit():
                idx = int(selection) - 1
                if 0 <= idx < len(fields):
                    field_name = fields[idx]
                    break
                else:
                    print(f"Invalid index. Please enter a number between 1 and {len(fields)}")
            elif selection in fields:
                field_name = selection
                break
            else:
                print(f"Field '{selection}' not found. Please try again.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return
    
    # Show unique values in the selected field
    field_data = get_scalar_field_data(las, field_name)
    if field_data is None:
        return
    
    unique_values = np.unique(field_data)
    value_counts = [(val, np.sum(field_data == val)) for val in unique_values]
    
    print(f"\nSelected field: '{field_name}'")
    print(f"Value distribution:")
    for val, count in value_counts:
        percentage = (count / len(field_data)) * 100
        print(f"  Value {val}: {count:,} points ({percentage:.2f}%)")
    
    # Common ground classification values
    print("\nCommon ground classification values:")
    print("  LAS Standard: 2 (Ground)")
    print("  Custom: 0, 1, or other values depending on your data")
    
    # Ask user for ground values
    print("\nEnter the value(s) that represent GROUND points (to be removed):")
    print("Separate multiple values with commas")
    print("Examples: '2' (LAS standard) or '0,1' or '2,8' (ground + noise)")
    
    while True:
        try:
            values_input = input("Ground value(s): ").strip()
            
            if not values_input:
                print("Please enter at least one value.")
                continue
            
            # Parse the input - handle both integers and floats
            value_strings = [v.strip() for v in values_input.split(',')]
            
            # Try to convert to the same type as the field data
            if field_data.dtype in [np.float32, np.float64]:
                ground_values = [float(v) for v in value_strings]
            else:
                ground_values = [int(float(v)) for v in value_strings]
            
            # Show what will be removed
            ground_count = np.sum(np.isin(field_data, ground_values))
            if ground_count == 0:
                print(f"Warning: No points found with value(s) {ground_values}")
                retry = input("Continue anyway? (y/n): ").strip().lower()
                if retry != 'y':
                    continue
            
            print(f"\nGround values to remove: {ground_values}")
            print(f"Points to be removed: {ground_count:,} ({(ground_count/len(field_data)*100):.2f}%)")
            print(f"Points to be kept: {len(field_data)-ground_count:,} ({((len(field_data)-ground_count)/len(field_data)*100):.2f}%)")
            
            confirm = input("\nProceed with ground removal? (y/n): ").strip().lower()
            if confirm == 'y':
                break
            else:
                print("Operation cancelled. You can re-enter the ground values.")
                
        except ValueError:
            print("Invalid input. Please enter numeric values separated by commas.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return
    
    # Remove ground points
    mask = remove_ground_points(las, field_name, ground_values)
    if mask is None or np.sum(mask) == 0:
        print("Error: No non-ground points remaining!")
        return
    
    # Generate output filename
    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}_no_ground.las"
    
    # Ask if user wants to change output path
    print(f"\nDefault output path: {output_file}")
    custom_output = input("Press Enter to use default, or enter custom output path: ").strip('"').strip("'")
    if custom_output:
        output_file = custom_output
    
    # Save filtered points
    save_filtered_points(las, mask, output_file)
    print("\nDone! Ground points have been removed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
