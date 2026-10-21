#!/usr/bin/env python3
"""
Identify Overlaps Script
Identifies overlapping dates between airborne LiDAR, Altum multispectral, and clipped LiDAR data collections.

This script scans the Data\\Airborne\\Output, Data\\Altum\\Model-Derived_BetterOrthos, and Data\\Clips folders
to find dates where both airborne LiDAR and multispectral data are available, plus clipped data.
"""

import os
import re
from pathlib import Path


def extract_dates_from_folder(folder_path, date_pattern=r'(\d{8})_'):
    """
    Extract dates from filenames in a folder using regex pattern.

    Args:
        folder_path (str): Path to the folder to scan
        date_pattern (str): Regex pattern to match dates (default: 8 digits followed by underscore)

    Returns:
        set: Set of date strings found
    """
    dates = set()

    if not os.path.exists(folder_path):
        print(f"Warning: Folder does not exist: {folder_path}")
        return dates

    # Scan all files and subdirectories
    for root, dirs, files in os.walk(folder_path):
        # Check files
        for file in files:
            match = re.search(date_pattern, file)
            if match:
                dates.add(match.group(1))

        # Check directory names
        for dir_name in dirs:
            match = re.search(date_pattern, dir_name)
            if match:
                dates.add(match.group(1))

    return dates


def main():
    """
    Main function to identify overlaps between airborne, Altum, and clips data.
    """
    print("Identify Overlaps - Airborne LiDAR vs Altum Multispectral vs Clips")
    print("=" * 70)

    # Define paths
    workspace_root = Path(__file__).parent.parent.parent  # Go up three levels from Scripts/python/ to workspace root
    airborne_output = workspace_root / "Data" / "Airborne" / "Output"
    altum_orthos = workspace_root / "Data" / "Altum" / "Model-Derived_BetterOrthos"
    clips_data = workspace_root / "Data" / "Clips"

    print(f"Scanning airborne output: {airborne_output}")
    print(f"Scanning Altum orthos: {altum_orthos}")
    print(f"Scanning clips data: {clips_data}")
    print()

    # Extract dates from all three sources
    airborne_dates = extract_dates_from_folder(str(airborne_output))
    altum_dates = extract_dates_from_folder(str(altum_orthos))
    clips_dates = extract_dates_from_folder(str(clips_data))

    # Sort dates for better display
    airborne_dates = sorted(airborne_dates)
    altum_dates = sorted(altum_dates)
    clips_dates = sorted(clips_dates)

    print("AIRBORNE LIDAR DATES:")
    print("-" * 30)
    for date in airborne_dates:
        print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
    print(f"Total airborne dates: {len(airborne_dates)}")
    print()

    print("ALTUM MULTISPECTRAL DATES:")
    print("-" * 30)
    for date in altum_dates:
        print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
    print(f"Total Altum dates: {len(altum_dates)}")
    print()

    print("CLIPS LIDAR DATES:")
    print("-" * 30)
    for date in clips_dates:
        print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
    print(f"Total clips dates: {len(clips_dates)}")
    print()

    # Find overlaps
    overlapping_dates = sorted(set(airborne_dates) & set(altum_dates) & set(clips_dates))

    print("FULL OVERLAPS (All Three: Airborne + Altum + Clips):")
    print("-" * 55)
    if overlapping_dates:
        for date in overlapping_dates:
            print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]}) ✓")
        print(f"\n✓ SUCCESS: Found {len(overlapping_dates)} complete overlaps!")
    else:
        print("  No complete overlaps found")
    print()

    # Find partial overlaps
    airborne_altum_overlap = sorted(set(airborne_dates) & set(altum_dates))
    airborne_clips_overlap = sorted(set(airborne_dates) & set(clips_dates))
    altum_clips_overlap = sorted(set(altum_dates) & set(clips_dates))

    print("PARTIAL OVERLAPS:")
    print("-" * 20)
    print(f"Airborne + Altum: {len(airborne_altum_overlap)} dates")
    print(f"Airborne + Clips: {len(airborne_clips_overlap)} dates")
    print(f"Altum + Clips: {len(altum_clips_overlap)} dates")
    print()

    # Find dates unique to each source
    airborne_only = sorted(set(airborne_dates) - set(altum_dates) - set(clips_dates))
    altum_only = sorted(set(altum_dates) - set(airborne_dates) - set(clips_dates))
    clips_only = sorted(set(clips_dates) - set(airborne_dates) - set(altum_dates))

    print("UNIQUE TO SINGLE SOURCE:")
    print("-" * 30)
    if airborne_only:
        print("Airborne-only dates:")
        for date in airborne_only:
            print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
        print(f"Total airborne-only: {len(airborne_only)}")
    else:
        print("No airborne-only dates")

    if altum_only:
        print("Altum-only dates:")
        for date in altum_only:
            print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
        print(f"Total Altum-only: {len(altum_only)}")
    else:
        print("No Altum-only dates")

    if clips_only:
        print("Clips-only dates:")
        for date in clips_only:
            print(f"  {date} ({date[:4]}-{date[4:6]}-{date[6:]})")
        print(f"Total clips-only: {len(clips_only)}")
    else:
        print("No clips-only dates")
    print()

    # Summary statistics
    print("SUMMARY:")
    print("-" * 20)
    print(f"Airborne LiDAR dates: {len(airborne_dates)}")
    print(f"Altum multispectral dates: {len(altum_dates)}")
    print(f"Clips LiDAR dates: {len(clips_dates)}")
    print(f"Complete overlaps (all 3): {len(overlapping_dates)}")
    print(f"Airborne+Altum overlaps: {len(airborne_altum_overlap)}")
    print(f"Airborne+Clips overlaps: {len(airborne_clips_overlap)}")
    print(f"Altum+Clips overlaps: {len(altum_clips_overlap)}")
    print()

    # Calculate overlap percentages
    if airborne_dates:
        complete_overlap_pct = (len(overlapping_dates) / len(airborne_dates)) * 100
        print(".1f")
    if altum_dates:
        altum_complete_pct = (len(overlapping_dates) / len(altum_dates)) * 100
        print(".1f")
    if clips_dates:
        clips_complete_pct = (len(overlapping_dates) / len(clips_dates)) * 100
        print(".1f")

    print("\n" + "=" * 70)
    print("OVERLAP ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()