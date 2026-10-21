import numpy as np

def get_unique_values_from_asc(asc_file_path):
    """
    Extract unique values from an ESRI ASCII Grid (.asc) file, excluding NODATA values.
    
    Parameters:
    asc_file_path (str): Path to the .asc file
    
    Returns:
    numpy.ndarray: Array of unique values in the grid
    """
    # Read the header
    header = {}
    with open(asc_file_path, 'r') as f:
        for line in f:
            if line.startswith('ncols'):
                header['ncols'] = int(line.split()[1])
            elif line.startswith('nrows'):
                header['nrows'] = int(line.split()[1])
            elif line.startswith('xllcorner'):
                header['xllcorner'] = float(line.split()[1])
            elif line.startswith('yllcorner'):
                header['yllcorner'] = float(line.split()[1])
            elif line.startswith('cellsize'):
                header['cellsize'] = float(line.split()[1])
            elif line.startswith('NODATA_value'):
                header['NODATA_value'] = float(line.split()[1])
            else:
                break
    
    # Read the grid data
    data = np.loadtxt(asc_file_path, skiprows=6)
    
    # Get NODATA value, default to -9999 if not specified
    nodata_value = header.get('NODATA_value', -9999)
    
    # Find unique values, excluding NODATA
    unique_values = np.unique(data[data != nodata_value])
    
    # Exclude -1 from the unique values
    unique_values = unique_values[unique_values != -1]
    
    return unique_values

# Example usage
if __name__ == "__main__":
    asc_file = r"Data\Airborne\Output\20250422_LLR_L2_NoOverlap_Orthometric\gridmetrics\20250422_LLR_L2_NoOverlap_Orthometric_clipped_1_normalized_gridmetrics_all_returns_all_metrics_elevation_mean.asc"  # Update this path
    uniques = get_unique_values_from_asc(asc_file)
    print("Unique values:", uniques)
    print("Total number of unique values:", len(uniques))
    if len(uniques) > 0:
        average = np.mean(uniques)
        print("Average of unique values:", average)
        sum_value = np.sum(uniques)
        print("Sum of unique values:", sum_value)
    else:
        print("No unique values found.")
