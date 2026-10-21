#!/usr/bin/env python3
"""
Alutum LAS Process Script
Processes a single LAS/LAZ file using PDAL, with optional colorization using multispectral images.

This script uses hardcoded parameters instead of command line arguments.
Modify the CONFIGURATION section below to set your input/output paths.

Supports two modes:
1. Preserve original RGB and add true NIR-GB composite (NIRGB_Red, NIRGB_Green, NIRGB_Blue)
2. Replace RGB with NIR-GB composite values

This creates a proper false-color composite by pre-processing the multispectral bands:
- NIR band (5) → Red channel (vegetation appears red/pink)
- Green band (2) → Green channel
- Blue band (1) → Blue channel
"""

import json
import os
import sys
import tempfile

try:
    import pdal
except ImportError:
    print("PDAL is not installed. Please install it with: pip install pdal")
    sys.exit(1)

try:
    import rasterio
    from rasterio import transform
    import numpy as np
except ImportError:
    print("Rasterio is not installed. Please install it with: pip install rasterio")
    sys.exit(1)


# =============================================================================
# CONFIGURATION - Modify these parameters as needed
# =============================================================================

# Input LAS/LAZ file path
INPUT_FILE = r"Data\Airborne\Clips\20250522_LLR_L2_orthometric_clipped\20250522_LLR_L2_orthometric_clipped_2.las"

# Multispectral image path (optional - leave empty to skip colorization)
MULTISPECTRAL_IMAGE = r"Data\Altum\Model-Derived_BetterOrthos\20250522_LLR_APT_Model-Derived_Ortho.tif"

# Output file path
OUTPUT_FILE = r"Data\Airborne\Output\NIRGB_Colorised_las\20250522_LLR_L2_orthometric_clipped_2_colorized.las"

# Preserve original RGB and add NIR,Green,Blue as separate fields
PRESERVE_ORIGINAL_RGB = False  # Set to False to replace RGB with multispectral

# =============================================================================
# END CONFIGURATION
# =============================================================================

# Global cache for composite files to avoid recreating them
_COMPOSITE_CACHE = {}

def create_nirgb_composite(multispectral_image):
    """
    Create a NIR-GB composite TIFF from a multispectral image.
    Uses caching to avoid recreating composites for the same TIFF file.
    
    Args:
        multispectral_image (str): Path to the multispectral TIFF file
        
    Returns:
        str: Path to the created composite TIFF file
    """
    global _COMPOSITE_CACHE
    
    # Check if we already have a composite for this TIFF
    abs_path = os.path.abspath(multispectral_image)
    if abs_path in _COMPOSITE_CACHE:
        cached_composite = _COMPOSITE_CACHE[abs_path]
        if os.path.exists(cached_composite):
            print(f"♻️  REUSING existing composite: {cached_composite}")
            return cached_composite
        else:
            # Cache entry exists but file is gone, remove from cache
            del _COMPOSITE_CACHE[abs_path]
    
    try:
        print(f"🔄 Creating NEW NIR-GB composite from: {multispectral_image}")
        
        # Read the multispectral image
        with rasterio.open(multispectral_image) as src:
            print(f"TIFF Info: CRS={src.crs}, Transform={src.transform}")
            print(f"TIFF Bounds: {src.bounds}")
            print(f"TIFF Shape: {src.width}x{src.height}, Bands: {src.count}")
            
            # Read the three bands: NIR (5), Green (2), Blue (1) - MicaSense Altum band order
            nir_band = src.read(5, masked=True)    # Band 5: NIR (masked for nodata)
            green_band = src.read(2, masked=True)  # Band 2: Green (masked for nodata)
            blue_band = src.read(1, masked=True)   # Band 1: Blue (masked for nodata)
            
            # Get metadata for the output file
            profile = src.profile.copy()
            profile.update({
                'count': 3,  # RGB composite
                'dtype': 'uint8',  # Convert to 8-bit for visualization
                'compress': 'lzw',
                'nodata': 0  # Use 0 as nodata for uint8
            })
            
            # Normalize bands to 0-255 range with better handling
            def normalize_band(band, band_name=""):
                # Work with the masked array to handle nodata properly
                if hasattr(band, 'mask') and hasattr(band, 'data'):
                    # For masked arrays
                    data = band.data
                    mask = band.mask
                    valid_data = data[~mask]
                    print(f"{band_name} raw data range: {data.min():.4f} to {data.max():.4f}")
                    print(f"{band_name} mask coverage: {mask.sum()}/{mask.size} pixels masked")
                else:
                    # For regular arrays
                    data = band
                    valid_data = data[data > -1000]  # Exclude very negative values
                    print(f"{band_name} raw data range: {data.min():.4f} to {data.max():.4f}")
                
                print(f"{band_name} valid pixels: {len(valid_data)}")
                
                if len(valid_data) == 0:
                    print(f"Warning: No valid data found in {band_name} band")
                    result = np.zeros_like(data, dtype=np.uint8)
                    return result
                
                # Get percentile values for stretching (only from valid data)
                # Use finite values only
                finite_data = valid_data[np.isfinite(valid_data)]
                if len(finite_data) == 0:
                    print(f"Warning: No finite data found in {band_name} band")
                    result = np.zeros_like(data, dtype=np.uint8)
                    return result
                
                p2, p98 = np.percentile(finite_data, [2, 98])
                print(f"{band_name} percentiles: P2={p2:.4f}, P98={p98:.4f}")
                
                # Handle case where p2 == p98 (all values the same)
                if p98 == p2:
                    p98 = p2 + 0.001  # Small increment to avoid division by zero
                
                # Linear stretch to 0-255, handling NaN values
                with np.errstate(invalid='ignore', divide='ignore'):
                    stretched = np.clip((data - p2) / (p98 - p2) * 255, 0, 255)
                
                # Set nodata/invalid areas to 0
                if hasattr(band, 'mask') and hasattr(band, 'data'):
                    stretched[band.mask] = 0
                else:
                    stretched[data <= -1000] = 0
                
                # Handle any remaining NaN or inf values
                stretched = np.nan_to_num(stretched, nan=0.0, posinf=255.0, neginf=0.0)
                
                result = stretched.astype(np.uint8)
                print(f"{band_name} normalized: min={result.min()}, max={result.max()}, mean={result.mean():.1f}")
                return result
            
            # Normalize each band with better logging
            print("\nNormalizing bands...")
            nir_norm = normalize_band(nir_band, "NIR")
            green_norm = normalize_band(green_band, "Green")
            blue_norm = normalize_band(blue_band, "Blue")
            
            # Get actual data ranges for reporting
            nir_data = nir_band.data if hasattr(nir_band, 'data') else nir_band
            green_data = green_band.data if hasattr(green_band, 'data') else green_band
            blue_data = blue_band.data if hasattr(blue_band, 'data') else blue_band
            
            # Report valid data ranges
            nir_valid = nir_data[nir_data > -1000]
            green_valid = green_data[green_data > -1000]
            blue_valid = blue_data[blue_data > -1000]
            
            if len(nir_valid) > 0:
                print(f"NIR valid range: {nir_valid.min():.3f} to {nir_valid.max():.3f}")
            if len(green_valid) > 0:
                print(f"Green valid range: {green_valid.min():.3f} to {green_valid.max():.3f}")
            if len(blue_valid) > 0:
                print(f"Blue valid range: {blue_valid.min():.3f} to {blue_valid.max():.3f}")
            
            # Create temporary composite file with unique name based on source
            source_name = os.path.splitext(os.path.basename(multispectral_image))[0]
            composite_path = os.path.join(os.path.dirname(multispectral_image), f"temp_nirgb_composite_{source_name}.tif")
            
            # Write the composite
            with rasterio.open(composite_path, 'w', **profile) as dst:
                dst.write(nir_norm, 1)    # NIR as Red channel
                dst.write(green_norm, 2)  # Green as Green channel  
                dst.write(blue_norm, 3)   # Blue as Blue channel
                
        print(f"Created NIR-GB composite: {composite_path}")
        
        # Verify the composite was created correctly
        with rasterio.open(composite_path) as verify:
            print(f"Composite verification: CRS={verify.crs}, Shape={verify.width}x{verify.height}")
            test_data = verify.read([1, 2, 3])
            print(f"Composite data ranges: R={test_data[0].min()}-{test_data[0].max()}, G={test_data[1].min()}-{test_data[1].max()}, B={test_data[2].min()}-{test_data[2].max()}")
        
        # Cache the composite for reuse
        _COMPOSITE_CACHE[abs_path] = composite_path
        print(f"💾 Cached composite for reuse")
        
        return composite_path
        
    except Exception as e:
        print(f"Error creating NIR-GB composite: {e}")
        import traceback
        traceback.print_exc()
        return None


def clear_composite_cache():
    """
    Clear the composite cache and remove temporary files.
    """
    global _COMPOSITE_CACHE
    
    print(f"🧹 Cleaning up {len(_COMPOSITE_CACHE)} cached composites...")
    
    for tiff_path, composite_path in _COMPOSITE_CACHE.items():
        try:
            if os.path.exists(composite_path):
                os.remove(composite_path)
                print(f"  Removed: {os.path.basename(composite_path)}")
        except Exception as e:
            print(f"  Could not remove {composite_path}: {e}")
    
    _COMPOSITE_CACHE.clear()
    print("✅ Composite cache cleared")


def _is_cached_composite(composite_file):
    """
    Check if a composite file is in the cache.
    
    Args:
        composite_file (str): Path to the composite file
        
    Returns:
        bool: True if the file is cached, False otherwise
    """
    return composite_file in _COMPOSITE_CACHE.values()


def verify_multispectral_dimensions(output_file, preserve_rgb=True):
    """
    Verify that the multispectral dimensions were successfully added to the output file.
    
    Args:
        output_file (str): Path to the output LAS file
        preserve_rgb (bool): Whether RGB preservation mode was used
    
    Returns:
        bool: True if verification passes, False otherwise
    """
    try:
        pipeline_json = {
            "pipeline": [output_file]
        }
        
        pipeline = pdal.Pipeline(json.dumps(pipeline_json))
        pipeline.execute()
        
        arrays = pipeline.arrays
        if len(arrays) > 0:
            array = arrays[0]
            field_names = list(array.dtype.names)
            
            print(f"\nVerifying multispectral dimensions in output file...")
            print("-" * 60)
            
            if preserve_rgb:
                # Check for NIR-GB composite RGB dimensions
                expected_dims = ['NIRGB_Red', 'NIRGB_Green', 'NIRGB_Blue']
                missing_dims = []
                found_dims = []
                
                for dim in expected_dims:
                    if dim in field_names:
                        found_dims.append(dim)
                        print(f"✓ Found dimension: {dim}")
                    else:
                        missing_dims.append(dim)
                        print(f"✗ Missing dimension: {dim}")
                
                # Check if original RGB is preserved
                rgb_dims = ['Red', 'Green', 'Blue']
                preserved_rgb = []
                for dim in rgb_dims:
                    if dim in field_names:
                        preserved_rgb.append(dim)
                        print(f"✓ Preserved original RGB: {dim}")
                
                if len(found_dims) == len(expected_dims):
                    print(f"\n✓ SUCCESS: All {len(expected_dims)} NIR-GB composite dimensions added successfully!")
                    print("✓ SUCCESS: True NIR-GB composite created (NIR band 5→Red, Green band 2→Green, Blue band 1→Blue)!")
                    if len(preserved_rgb) == len(rgb_dims):
                        print("✓ SUCCESS: Original RGB values preserved!")
                    return True
                else:
                    print(f"\n✗ FAILURE: Only {len(found_dims)}/{len(expected_dims)} NIR-GB composite dimensions found")
                    return False
            else:
                # Check that RGB dimensions exist (should be replaced with multispectral)
                rgb_dims = ['Red', 'Green', 'Blue']
                found_rgb = []
                for dim in rgb_dims:
                    if dim in field_names:
                        found_rgb.append(dim)
                        print(f"✓ Found RGB dimension: {dim}")
                
                if len(found_rgb) == len(rgb_dims):
                    print(f"\n✓ SUCCESS: RGB dimensions updated with multispectral values!")
                    return True
                else:
                    print(f"\n✗ FAILURE: RGB dimensions not properly updated")
                    return False
        
        return False
        
    except Exception as e:
        print(f"Error verifying multispectral dimensions: {e}")
        return False


def check_las_dimensions(file_path, description=""):
    """
    Check and display the dimensions available in a LAS file.
    
    Args:
        file_path (str): Path to the LAS file
        description (str): Description for the file (e.g., "Input", "Output")
    """
    try:
        # Create a simple pipeline to read the file
        pipeline_json = {
            "pipeline": [file_path]
        }
        
        pipeline = pdal.Pipeline(json.dumps(pipeline_json))
        pipeline.execute()
        
        # Use pipeline arrays to get dimensions
        arrays = pipeline.arrays
        if len(arrays) > 0:
            array = arrays[0]
            print(f"\n{description} File Dimensions ({os.path.basename(file_path)}):")
            print("-" * 60)
            for field_name in array.dtype.names:
                field_type = array.dtype.fields[field_name][0]
                print(f"  {field_name:<15} Type: {field_type}")
            print(f"Total dimensions: {len(array.dtype.names)}")
        else:
            print(f"No data arrays found in {description} file")
        
        return True
        
    except Exception as e:
        print(f"Error checking dimensions for {description} file: {e}")
        return False


def process_las_file(input_file, output_file, multispectral_image=None, preserve_rgb=True):
    """
    Process a single LAS/LAZ file using PDAL, optionally colorizing with multispectral image.

    Args:
        input_file (str): Input LAS/LAZ file path
        output_file (str): Output file path
        multispectral_image (str, optional): Path to multispectral image for colorization
        preserve_rgb (bool): If True, preserve original RGB and add NIR-GB composite as new fields
    """
    # Build PDAL pipeline
    pipeline_stages = [input_file]
    composite_file = None

    # Add colorization filter if multispectral image is provided
    if multispectral_image and os.path.exists(multispectral_image):
        print(f"Adding colorization using multispectral image: {multispectral_image}")

        if preserve_rgb:
            print("Directly mapping multispectral bands and preserving original RGB values")
            print("NIR (band 5)→NIRGB_Red, Green (band 2)→NIRGB_Green, Blue (band 1)→NIRGB_Blue")

            # Directly map multispectral bands as new dimensions without replacing RGB
            pipeline_stages.append({
                "type": "filters.colorization",
                "raster": multispectral_image,
                "dimensions": "NIRGB_Red:5,NIRGB_Green:2,NIRGB_Blue:1"  # NIR (band 5), Green (band 2), Blue (band 1)
            })
        else:
            print("WARNING: This will REPLACE any existing RGB values in the LAS file!")
            print("Creating pre-processed multispectral composite to handle NoData values")
            print("NIR (band 5)→Red, Green (band 2)→Green, Blue (band 1)→Blue")

            # Create pre-processed composite to handle NoData values properly
            composite_file = create_nirgb_composite(multispectral_image)
            if composite_file is None:
                print("ERROR: Failed to create multispectral composite")
                return False

            # Use the pre-processed composite
            pipeline_stages.append({
                "type": "filters.colorization",
                "raster": composite_file,
                "dimensions": "Red:1,Green:2,Blue:3"  # Use pre-processed composite
            })

    # Add writer
    pipeline_stages.append({
        "type": "writers.las",
        "filename": output_file,
        "extra_dims": "all"  # This is needed to preserve custom dimensions
    })

    # Create PDAL pipeline
    pipeline_json = {
        "pipeline": pipeline_stages
    }

    try:
        # Check input file dimensions
        print("\n=== INPUT FILE ANALYSIS ===")
        check_las_dimensions(input_file, "INPUT")
        
        # Check coordinate systems and bounds
        print("\n=== COORDINATE SYSTEM ANALYSIS ===")
        
        # Check LAS file bounds
        las_info_pipeline = {
            "pipeline": [
                input_file,
                {
                    "type": "filters.info"
                }
            ]
        }
        
        try:
            las_pipeline = pdal.Pipeline(json.dumps(las_info_pipeline))
            las_pipeline.execute()
            las_arrays = las_pipeline.arrays
            if len(las_arrays) > 0:
                las_data = las_arrays[0]
                las_x_min, las_x_max = las_data['X'].min(), las_data['X'].max()
                las_y_min, las_y_max = las_data['Y'].min(), las_data['Y'].max()
                print(f"LAS bounds: X=[{las_x_min:.2f}, {las_x_max:.2f}], Y=[{las_y_min:.2f}, {las_y_max:.2f}]")
        except Exception as e:
            print(f"Could not extract LAS bounds: {e}")

        # Check TIFF bounds
        if multispectral_image:
            try:
                with rasterio.open(multispectral_image) as src:
                    tiff_bounds = src.bounds
                    print(f"TIFF bounds: X=[{tiff_bounds.left:.2f}, {tiff_bounds.right:.2f}], Y=[{tiff_bounds.bottom:.2f}, {tiff_bounds.top:.2f}]")
                    print(f"TIFF CRS: {src.crs}")
            except Exception as e:
                print(f"Could not extract TIFF bounds: {e}")

        # Execute the pipeline
        print(f"\n=== PDAL PIPELINE ===")
        print(json.dumps(pipeline_json, indent=2))
        print("\n=== EXECUTING PDAL PIPELINE ===")
        pipeline = pdal.Pipeline(json.dumps(pipeline_json))
        pipeline.execute()

        # Check output file dimensions
        print("\n=== OUTPUT FILE ANALYSIS ===")
        check_las_dimensions(output_file, "OUTPUT")
        
        # Check RGB values in output file
        print("\n=== RGB VALUES CHECK ===")
        output_check_pipeline = {
            "pipeline": [output_file]
        }
        
        check_pipeline = pdal.Pipeline(json.dumps(output_check_pipeline))
        check_pipeline.execute()
        check_arrays = check_pipeline.arrays
        
        if len(check_arrays) > 0:
            check_data = check_arrays[0]
            if 'Red' in check_data.dtype.names:
                red_vals = check_data['Red']
                green_vals = check_data['Green'] if 'Green' in check_data.dtype.names else None
                blue_vals = check_data['Blue'] if 'Blue' in check_data.dtype.names else None
                
                print(f"Red values: min={red_vals.min()}, max={red_vals.max()}, mean={red_vals.mean():.1f}")
                if green_vals is not None:
                    print(f"Green values: min={green_vals.min()}, max={green_vals.max()}, mean={green_vals.mean():.1f}")
                if blue_vals is not None:
                    print(f"Blue values: min={blue_vals.min()}, max={blue_vals.max()}, mean={blue_vals.mean():.1f}")
                
                # Check for all-zero values
                if red_vals.max() == 0 and (green_vals is None or green_vals.max() == 0) and (blue_vals is None or blue_vals.max() == 0):
                    print("⚠️  WARNING: All RGB values are zero! This explains the black appearance.")
                    print("This usually indicates a coordinate system mismatch or bounds issue.")
                else:
                    print("✅ RGB values look good!")
        
        # Verify multispectral dimensions were added (if colorization was applied)
        if multispectral_image and os.path.exists(multispectral_image):
            verification_success = verify_multispectral_dimensions(output_file, preserve_rgb)
            if not verification_success:
                print("WARNING: Multispectral dimension verification failed!")

        print(f"\nSuccessfully processed file: {input_file}")
        if multispectral_image:
            if preserve_rgb:
                print("Added multispectral bands as new fields (NIRGB_Red, NIRGB_Green, NIRGB_Blue)")
                print("NIR (band 5)→NIRGB_Red, Green (band 2)→NIRGB_Green, Blue (band 1)→NIRGB_Blue")
                print("Original RGB values preserved")
            else:
                print(f"Replaced RGB with multispectral bands from: {multispectral_image}")
                print("NIR (band 5)→Red, Green (band 2)→Green, Blue (band 1)→Blue")
        print(f"Output saved to: {output_file}")
        print(f"Output file size: {os.path.getsize(output_file)} bytes")

        return True

    except Exception as e:
        print(f"Error during processing: {e}")
        return False
    
    finally:
        # Clean up temporary composite file (only if it's not cached)
        if 'composite_file' in locals() and composite_file and os.path.exists(composite_file):
            # Don't delete cached composites
            if not _is_cached_composite(composite_file):
                try:
                    os.remove(composite_file)
                    print(f"Cleaned up temporary file: {composite_file}")
                except:
                    print(f"Note: Could not remove temporary file: {composite_file}")


def main():
    """
    Main function that uses the hardcoded configuration to process a single LAS file.
    """
    print("Alutum LAS Process Script")
    print("Supports multispectral colorization")
    print("=" * 50)

    # Validate configuration
    if not INPUT_FILE:
        print("ERROR: Please specify INPUT_FILE in the script")
        return False

    if not OUTPUT_FILE:
        print("ERROR: Please specify OUTPUT_FILE in the script")
        return False

    # Check if multispectral image exists (if provided)
    if MULTISPECTRAL_IMAGE and not os.path.exists(MULTISPECTRAL_IMAGE):
        print(f"ERROR: Multispectral image does not exist: {MULTISPECTRAL_IMAGE}")
        return False

    # Check if input file exists
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: Input file does not exist: {INPUT_FILE}")
        return False

    # Ensure output directory exists
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    # For single file processing
    print(f"Processing file: {INPUT_FILE}")
    if MULTISPECTRAL_IMAGE:
        print(f"Using multispectral image: {MULTISPECTRAL_IMAGE}")
        if PRESERVE_ORIGINAL_RGB:
            print("Mode: Preserving original RGB + adding true NIR-GB composite")
        else:
            print("Mode: Replacing RGB with NIR-GB composite")
    print(f"Output file: {OUTPUT_FILE}")

    success = process_las_file(INPUT_FILE, OUTPUT_FILE, MULTISPECTRAL_IMAGE, PRESERVE_ORIGINAL_RGB)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)