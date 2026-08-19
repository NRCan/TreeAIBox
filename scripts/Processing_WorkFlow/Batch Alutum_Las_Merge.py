#!/usr/bin/env python3
"""
Batch Alutum LAS Process Script
Processes multiple LAS files in a folder using the Alutum_Las_Merge.py processing function.

This script automatically finds all LAS files in a specified folder and processes them
using the same multispectral colorization logic from Alutum_Las_Merge.py.
"""

import os
import sys
import glob
from pathlib import Path
import time
import re

# Add the current directory to Python path to import our processing function
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from Alutum_Las_Merge import process_las_file, clear_composite_cache
    print("✅ Successfully imported processing function from Alutum_Las_Merge.py")
except ImportError as e:
    print(f"❌ ERROR: Could not import processing function: {e}")
    print("Make sure Alutum_Las_Merge.py is in the same directory as this script.")
    sys.exit(1)

# =============================================================================
# CONFIGURATION - Modify these parameters as needed
# =============================================================================

# Input folder containing LAS files to process
INPUT_FOLDER = r"Data\Airborne\Clips\20250626_LLR_L2_orthometric_clipped"

# Multispectral image path (same TIFF for all files from this date)
MULTISPECTRAL_IMAGE = r"Data\Altum\Model-Derived_BetterOrthos\20250626_LLR_APT_Model-Derived_Ortho.tif"

# Output folder for colorized LAS files
OUTPUT_FOLDER = r"Data\Airborne\Output\NIRGB_Colorised_las"

# Preserve original RGB and add NIR,Green,Blue as separate fields
PRESERVE_ORIGINAL_RGB = False  # Set to False to replace RGB with multispectral

# File pattern to match (*.las or *.laz)
FILE_PATTERN = "*.las"

# =============================================================================
# END CONFIGURATION
# =============================================================================


def find_las_files(input_folder, pattern="*.las"):
    """
    Find all LAS files in the input folder matching the pattern.
    
    Args:
        input_folder (str): Path to the folder containing LAS files
        pattern (str): File pattern to match (e.g., "*.las", "*.laz")
        
    Returns:
        list: List of LAS file paths found
    """
    search_path = os.path.join(input_folder, pattern)
    las_files = glob.glob(search_path)
    las_files.sort()  # Sort for consistent processing order
    return las_files


def extract_date_from_filename(filename):
    """
    Extract date from LAS filename.
    Expects format like: 20250522_LLR_L2_orthometric_clipped_1.las
    
    Args:
        filename (str): Name of the LAS file
        
    Returns:
        str: Date string (YYYYMMDD) or None if not found
    """
    # Look for 8-digit date pattern at the beginning of filename
    date_match = re.match(r'^(\d{8})_', filename)
    if date_match:
        return date_match.group(1)
    
    # Alternative pattern - look for any 8-digit sequence
    date_match = re.search(r'(\d{8})', filename)
    if date_match:
        return date_match.group(1)
    
    return None


def generate_output_path(input_file, base_output_folder):
    """
    Generate output file path based on input file name with date-specific folder.
    
    Args:
        input_file (str): Path to input LAS file
        base_output_folder (str): Base output folder path
        
    Returns:
        str: Output file path with "_colorized" suffix in date-specific folder
    """
    input_name = os.path.basename(input_file)
    name_without_ext = os.path.splitext(input_name)[0]
    output_name = f"{name_without_ext}_colorized.las"
    
    # Extract date from filename
    date_str = extract_date_from_filename(input_name)
    
    if date_str:
        # Format date for folder name: YYYYMMDD -> YYYY-MM-DD
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        date_folder = f"{date_str}_NIRGB_Colorised_las"  # e.g., "20250522_NIRGB_Colorised_las"
        output_folder = os.path.join(base_output_folder, date_folder)
    else:
        # Fallback to base folder if date extraction fails
        print(f"⚠️  Could not extract date from {input_name}, using base output folder")
        output_folder = base_output_folder
    
    return os.path.join(output_folder, output_name)


def batch_process_las_files():
    """
    Main batch processing function that processes all LAS files in the input folder.
    """
    print("🚀 Batch Alutum LAS Processing Script")
    print("=" * 60)
    
    # Validate configuration
    if not os.path.exists(INPUT_FOLDER):
        print(f"❌ ERROR: Input folder does not exist: {INPUT_FOLDER}")
        return False
    
    if MULTISPECTRAL_IMAGE and not os.path.exists(MULTISPECTRAL_IMAGE):
        print(f"❌ ERROR: Multispectral image does not exist: {MULTISPECTRAL_IMAGE}")
        return False
    
    # Create output folder if it doesn't exist
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"📁 Created base output folder: {OUTPUT_FOLDER}")
    
    # Find all LAS files to process
    las_files = find_las_files(INPUT_FOLDER, FILE_PATTERN)
    
    if not las_files:
        print(f"❌ No LAS files found in {INPUT_FOLDER} matching pattern {FILE_PATTERN}")
        return False
    
    # Extract dates and show file organization
    date_files = {}
    for file_path in las_files:
        filename = os.path.basename(file_path)
        date_str = extract_date_from_filename(filename)
        if date_str not in date_files:
            date_files[date_str] = []
        date_files[date_str].append(filename)
    
    print(f"📋 Found {len(las_files)} LAS files organized by date:")
    for date_str, files in date_files.items():
        if date_str:
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            print(f"   📅 {formatted_date} ({date_str}): {len(files)} files")
            for filename in files:
                print(f"      • {filename}")
        else:
            print(f"   ❓ Unknown date: {len(files)} files")
            for filename in files:
                print(f"      • {filename}")
    
    print(f"\n🎯 Configuration:")
    print(f"   Input Folder: {INPUT_FOLDER}")
    print(f"   Base Output Folder: {OUTPUT_FOLDER}")
    print(f"   Date-specific folders will be created automatically")
    print(f"   Multispectral Image: {os.path.basename(MULTISPECTRAL_IMAGE) if MULTISPECTRAL_IMAGE else 'None'}")
    print(f"   Mode: {'Preserve RGB + Add NIR-GB composite' if PRESERVE_ORIGINAL_RGB else 'Replace RGB with NIR-GB composite'}")
    
    # Process each file
    total_files = len(las_files)
    successful = 0
    failed = 0
    skipped = 0
    
    start_time = time.time()
    
    print(f"\n🔄 Starting batch processing...")
    print("=" * 60)
    
    for i, input_file in enumerate(las_files, 1):
        filename = os.path.basename(input_file)
        output_file = generate_output_path(input_file, OUTPUT_FOLDER)
        
        # Create the date-specific output folder if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"📁 Created date-specific folder: {os.path.basename(output_dir)}")
        
        print(f"\n[{i}/{total_files}] Processing: {filename}")
        print(f"📁 Output folder: {os.path.basename(output_dir)}")
        print("-" * 40)
        
        # Check if output file already exists
        if os.path.exists(output_file):
            print(f"⚠️  Output file already exists: {os.path.basename(output_file)}")
            user_choice = input("Do you want to overwrite it? (y/n/skip): ").lower().strip()
            
            if user_choice == 'skip' or user_choice == 's':
                print(f"⏭️  Skipping {filename}")
                skipped += 1
                continue
            elif user_choice != 'y' and user_choice != 'yes':
                print(f"⏭️  Skipping {filename}")
                skipped += 1
                continue
        
        # Process the file
        try:
            print(f"🔄 Processing {filename}...")
            success = process_las_file(
                input_file=input_file,
                output_file=output_file,
                multispectral_image=MULTISPECTRAL_IMAGE,
                preserve_rgb=PRESERVE_ORIGINAL_RGB
            )
            
            if success:
                print(f"✅ Successfully processed: {filename}")
                print(f"💾 Output saved to: {os.path.basename(output_file)}")
                if os.path.exists(output_file):
                    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                    print(f"📁 File size: {file_size_mb:.1f} MB")
                successful += 1
            else:
                print(f"❌ Failed to process: {filename}")
                failed += 1
                
        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        
        # Show progress
        processed = successful + failed + skipped
        remaining = total_files - processed
        elapsed = time.time() - start_time
        
        if processed > 0:
            avg_time = elapsed / processed
            eta_seconds = avg_time * remaining
            eta_mins = eta_seconds / 60
            print(f"⏱️  Progress: {processed}/{total_files} | ETA: {eta_mins:.1f} mins")
    
    # Final summary
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("🏁 BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"📊 Summary:")
    print(f"   Total files: {total_files}")
    print(f"   ✅ Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏭️  Skipped: {skipped}")
    print(f"   ⏱️  Total time: {total_time/60:.1f} minutes")
    
    if successful > 0:
        print(f"   ⚡ Average time per file: {total_time/successful:.1f} seconds")
    
    # Clean up cached composites
    try:
        clear_composite_cache()
    except Exception as e:
        print(f"Note: Could not clear composite cache: {e}")
    
    return successful > 0


if __name__ == "__main__":
    success = batch_process_las_files()
    sys.exit(0 if success else 1)