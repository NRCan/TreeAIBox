#!/usr/bin/env python3
"""
Create Matched Processing Pairs Script
Creates matched pairs of LAS clips and corresponding TIFF files for batch processing.

This script identifies the 7 overlapping dates and creates a structured approach
for processing each LAS clip with its corresponding multispectral TIFF file.
"""

import os
import json
from pathlib import Path


def create_matched_pairs():
    """
    Create matched pairs of LAS clips and TIFF files for the 7 overlapping dates.
    """
    print("Create Matched Processing Pairs")
    print("=" * 50)

    # Define workspace root
    workspace_root = Path(__file__).parent.parent.parent

    # Define the 7 overlapping dates
    overlapping_dates = [
        "20250407", "20250522", "20250527", "20250606",
        "20250613", "20250619", "20250626"
    ]

    # Define paths
    clips_base = workspace_root / "Data" / "Airborne" / "Clips"
    altum_base = workspace_root / "Data" / "Altum" / "Model-Derived_BetterOrthos"
    matched_output_base = workspace_root / "Data" / "Matched_Processing_Pairs"

    print(f"Clips base: {clips_base}")
    print(f"Altum base: {altum_base}")
    print(f"Matched output: {matched_output_base}")
    print()

    # Create matched pairs structure
    matched_pairs = {}

    for date in overlapping_dates:
        print(f"Processing date: {date} ({date[:4]}-{date[4:6]}-{date[6:]})")

        # Find corresponding TIFF file - try both naming patterns
        tiff_patterns = [
            f"{date}_LLR_APT_Model-Derived_Ortho.tif",  # Preferred pattern
            f"{date}_LLR_APT_Model.tif"                  # Alternative pattern
        ]
        
        tiff_path = None
        for pattern in tiff_patterns:
            candidate = altum_base / pattern
            if candidate.exists():
                tiff_path = candidate
                break

        if tiff_path is None:
            print(f"  WARNING: TIFF file not found for date {date} (tried patterns: {tiff_patterns})")
            continue

        print(f"  Found TIFF: {tiff_path.name}")

        # Find corresponding clips folder
        clips_folder = clips_base / f"{date}_LLR_L2_orthometric_clipped"

        if not clips_folder.exists():
            print(f"  WARNING: Clips folder not found: {clips_folder}")
            continue

        # Get all LAS clips in the folder
        las_files = list(clips_folder.glob("*.las"))
        las_files.sort()  # Sort for consistent ordering

        print(f"  Found {len(las_files)} LAS clips")

        # Create matched pairs for this date
        date_pairs = []
        for las_file in las_files:
            pair = {
                "date": date,
                "las_file": str(las_file),
                "las_filename": las_file.name,
                "tiff_file": str(tiff_path),
                "tiff_filename": tiff_path.name,
                "output_folder": f"Data/Matched_Processing_Pairs/{date}",
                "suggested_output": f"Data/Matched_Processing_Pairs/{date}/{las_file.stem}_colorized.las"
            }
            date_pairs.append(pair)

        matched_pairs[date] = {
            "date": date,
            "tiff_file": str(tiff_path),
            "clips_folder": str(clips_folder),
            "num_clips": len(las_files),
            "pairs": date_pairs
        }

        print(f"  Created {len(date_pairs)} processing pairs")
        print()

    # Create output directory structure
    print("Creating output directory structure...")
    for date in matched_pairs:
        output_dir = matched_output_base / date
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {output_dir}")

    # Save matched pairs to JSON file
    json_output = matched_output_base / "matched_pairs.json"
    with open(json_output, 'w') as f:
        json.dump(matched_pairs, f, indent=2)

    print(f"Saved matched pairs configuration to: {json_output}")

    # Create batch processing script
    create_batch_script(matched_pairs, matched_output_base)

    # Print summary
    print("\n" + "=" * 50)
    print("MATCHED PAIRS SUMMARY")
    print("=" * 50)

    total_pairs = 0
    for date, data in matched_pairs.items():
        pairs_count = data["num_clips"]
        total_pairs += pairs_count
        print(f"{date}: {pairs_count} LAS clips -> 1 TIFF file = {pairs_count} processing pairs")

    print(f"\nTOTAL: {total_pairs} matched processing pairs across {len(matched_pairs)} dates")
    print(f"Each pair consists of: 1 LAS clip + 1 multispectral TIFF")

    return matched_pairs


def create_batch_script(matched_pairs, output_base):
    """
    Create a batch processing script for the matched pairs.
    """
    batch_script_content = '''#!/usr/bin/env python3
"""
Batch Processing Script for Matched LAS-TIFF Pairs
Processes all matched pairs using the Alutum_Las_Merge.py script.
"""

import os
import sys
import json
from pathlib import Path

def batch_process_matched_pairs():
    """
    Batch process all matched pairs.
    """
    print("Batch Processing Matched LAS-TIFF Pairs")
    print("=" * 50)

    # Load matched pairs configuration
    config_file = Path(__file__).parent / "matched_pairs.json"
    with open(config_file, 'r') as f:
        matched_pairs = json.load(f)

    total_processed = 0
    total_success = 0

    for date, data in matched_pairs.items():
        print(f"\\nProcessing date: {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
        print("-" * 40)

        tiff_file = data["tiff_file"]

        for pair in data["pairs"]:
            las_file = pair["las_file"]
            output_file = pair["suggested_output"]

            # Ensure output directory exists
            output_dir = Path(output_file).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"  Processing: {Path(las_file).name}")
            print(f"  With TIFF:  {Path(tiff_file).name}")
            print(f"  Output:     {Path(output_file).name}")

            total_processed += 1

            # Import and run processing function
            scripts_dir = Path(__file__).parent.parent.parent / "Scripts" / "python"
            sys.path.insert(0, str(scripts_dir))

            try:
                from Alutum_Las_Merge import process_las_file

                success = process_las_file(
                    input_file=las_file,
                    output_file=output_file,
                    multispectral_image=tiff_file,
                    preserve_rgb=False  # Replace RGB with multispectral
                )

                if success:
                    total_success += 1
                    print("    SUCCESS")
                else:
                    print("    FAILED")
            except Exception as e:
                print(f"    ERROR: {e}")

    print("\\n" + "=" * 50)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 50)
    print(f"Total pairs processed: {total_processed}")
    print(f"Successful: {total_success}")
    print(f"Failed: {total_processed - total_success}")
    success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")

if __name__ == "__main__":
    batch_process_matched_pairs()
'''

    batch_script_path = output_base / "batch_process_matched_pairs.py"
    with open(batch_script_path, 'w') as f:
        f.write(batch_script_content)

    print(f"Created batch processing script: {batch_script_path}")


def main():
    """
    Main function.
    """
    matched_pairs = create_matched_pairs()

    print("\n" + "=" * 50)
    print("NEXT STEPS:")
    print("=" * 50)
    print("1. Review the matched pairs in: Data/Matched_Processing_Pairs/matched_pairs.json")
    print("2. Run batch processing with: python Data/Matched_Processing_Pairs/batch_process_matched_pairs.py")
    print("3. Each of the 56 LAS clips will be processed with its corresponding multispectral TIFF")
    print("4. Output will be saved in date-organized folders within Data/Matched_Processing_Pairs/")


if __name__ == "__main__":
    main()