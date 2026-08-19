"""
Filter point cloud by scalar field values
Extracts points that match specific scalar field values
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
        title="Select LAS/LAZ file to filter",
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


def filter_points_by_values(las, field_name, values):
    """Filter points based on scalar field values"""
    field_data = get_scalar_field_data(las, field_name)
    if field_data is None:
        return None
    
    # Create boolean mask for points matching any of the values
    mask = np.isin(field_data, values)
    
    # Get unique values in the field for statistics
    unique_values = np.unique(field_data)
    print(f"\nAvailable values in '{field_name}': {unique_values}")
    print(f"Total points: {len(las.points)}")
    print(f"Matching points: {np.sum(mask)}")
    
    return mask


def save_filtered_points(las, mask, output_path):
    """Save filtered points to a new LAS file"""
    # Create a new LAS file with the filtered points
    filtered_las = laspy.LasData(las.header)
    filtered_las.points = las.points[mask]
    
    # Write to file
    filtered_las.write(output_path)
    print(f"\nFiltered point cloud saved to: {output_path}")


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
    print("Available Scalar Fields:")
    print("="*60)
    for i, field in enumerate(fields, 1):
        try:
            data = get_scalar_field_data(las, field)
            if data is not None:
                unique_vals = np.unique(data)
                print(f"{i:2d}. {field:20s} - Range: [{np.min(data):.2f}, {np.max(data):.2f}], Unique values: {len(unique_vals)}")
        except:
            print(f"{i:2d}. {field:20s} - (unable to read)")
    print("="*60)
    
    # Ask user to select a field
    while True:
        try:
            selection = input("\nEnter the number or name of the scalar field to filter by: ").strip()
            
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
    print(f"\nSelected field: '{field_name}'")
    print(f"Unique values in this field: {unique_values}")
    
    # Ask user for filter values
    print("\nEnter the value(s) to extract (separate multiple values with commas):")
    print("Examples: '2' or '1,2,3' or '2.5,3.0'")
    
    while True:
        try:
            values_input = input("Values: ").strip()
            
            # Parse the input - handle both integers and floats
            value_strings = [v.strip() for v in values_input.split(',')]
            
            # Try to convert to the same type as the field data
            if field_data.dtype in [np.float32, np.float64]:
                values = [float(v) for v in value_strings]
            else:
                values = [int(float(v)) for v in value_strings]
            
            print(f"Filtering for values: {values}")
            break
        except ValueError:
            print("Invalid input. Please enter numeric values separated by commas.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return
    
    # Filter points
    mask = filter_points_by_values(las, field_name, values)
    if mask is None or np.sum(mask) == 0:
        print("No points match the specified values.")
        return
    
    # Generate output filename
    base_name = os.path.splitext(input_file)[0]
    value_str = "_".join([str(v).replace('.', 'p') for v in values])
    output_file = f"{base_name}_filtered_{field_name}_{value_str}.las"
    
    # Ask if user wants to change output path
    print(f"\nDefault output path: {output_file}")
    custom_output = input("Press Enter to use default, or enter custom output path: ").strip('"').strip("'")
    if custom_output:
        output_file = custom_output
    
    # Save filtered points
    save_filtered_points(las, mask, output_file)
    print("\nDone!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
