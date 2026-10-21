#!/usr/bin/env python3
"""
LAS File Renamer

This script renames LAS files to a standardized format: YYYYMMDD_LLR_L2.las
It removes all suffixes after the LLR_L2 identifier.

Usage:
    python las_renamer.py [options] <input_directory>

Options:
    -p, --pattern PATTERN   Pattern to match for renaming (default: *_LLR_L2*.las)
    --suffix SUFFIX        Suffix to add to filenames (e.g., "_orthometric")
    -v, --verbose          Verbose output
    --dry-run              Show what would be renamed without actually doing it
    --backup               Create backup of original filenames

Examples:
    # Rename all LAS files in processed_las directory
    python las_renamer.py "Data/Airborne/Input/processed_las/"

    # Add orthometric suffix to all files
    python las_renamer.py --suffix "_orthometric" "Data/Airborne/Input/processed_las/"

    # Dry run to see what would be renamed
    python las_renamer.py --dry-run "Data/Airborne/Input/processed_las/"

    # Verbose output with backup
    python las_renamer.py -v --backup "Data/Airborne/Input/processed_las/"
"""

import os
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime


class LASRenamer:
    """Class to handle LAS file renaming"""

    def __init__(self):
        self.backup_file = None

    def extract_date_and_base(self, filename, suffix=""):
        """
        Extract date and base name from filename

        Args:
            filename (str): Original filename
            suffix (str): Suffix to add to the new filename

        Returns:
            tuple: (new_filename, date_str) or (None, None) if pattern doesn't match
        """
        # Pattern to match: YYYYMMDD_LLR_L2 followed by anything until .las
        pattern = r'^(\d{8})_LLR_L2.*\.las$'

        match = re.match(pattern, filename)
        if match:
            date_str = match.group(1)
            new_filename = f"{date_str}_LLR_L2{suffix}.las"
            return new_filename, date_str

        return None, None

    def create_backup(self, directory, filenames_mapping):
        """
        Create a backup file with original -> new filename mapping

        Args:
            directory (str): Directory path
            filenames_mapping (dict): Dictionary of old -> new filenames
        """
        backup_path = Path(directory) / "filename_backup.txt"
        self.backup_file = str(backup_path)

        with open(backup_path, 'w') as f:
            f.write("LAS FILE RENAME BACKUP\n")
            f.write("=" * 50 + "\n")
            f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Directory: {directory}\n\n")

            for old_name, new_name in filenames_mapping.items():
                f.write(f"{old_name} -> {new_name}\n")

        print(f"Backup created: {backup_path}")

    def rename_files(self, directory, pattern="*_LLR_L2*.las", suffix="", verbose=False,
                    dry_run=False, create_backup=False):
        """
        Rename LAS files to standardized format

        Args:
            directory (str): Directory containing LAS files
            pattern (str): Glob pattern to match files
            verbose (bool): Verbose output
            dry_run (bool): Show what would be done without actually renaming
            create_backup (bool): Create backup file with filename mapping

        Returns:
            dict: Renaming results and statistics
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # Find all LAS files matching the pattern
        las_files = list(dir_path.glob(pattern))
        las_files = [f for f in las_files if f.is_file()]

        if not las_files:
            print(f"No LAS files found matching pattern '{pattern}' in {directory}")
            return {'files_found': 0, 'renamed': 0, 'skipped': 0, 'errors': 0}

        print(f"Found {len(las_files)} LAS files matching pattern '{pattern}'")

        # Analyze files and plan renames
        rename_plan = {}
        skipped = []
        errors = []

        for las_file in las_files:
            filename = las_file.name
            new_name, date_str = self.extract_date_and_base(filename, suffix)

            if new_name:
                new_path = las_file.parent / new_name

                # Check for conflicts
                if new_path.exists() and new_path != las_file:
                    errors.append({
                        'file': filename,
                        'error': f'Conflict: {new_name} already exists'
                    })
                    continue

                if new_name != filename:
                    rename_plan[str(las_file)] = {
                        'old_name': filename,
                        'new_name': new_name,
                        'old_path': str(las_file),
                        'new_path': str(new_path)
                    }
                else:
                    skipped.append(filename)
            else:
                errors.append({
                    'file': filename,
                    'error': 'Filename does not match expected pattern'
                })

        # Create backup if requested
        if create_backup and rename_plan and not dry_run:
            backup_mapping = {info['old_name']: info['new_name'] for info in rename_plan.values()}
            self.create_backup(directory, backup_mapping)

        # Report plan
        if rename_plan:
            print(f"\nFiles to rename: {len(rename_plan)}")
            if verbose or dry_run:
                print("\nRename plan:")
                print("-" * 60)
                for old_path, info in rename_plan.items():
                    print(f"  {info['old_name']}")
                    print(f"    -> {info['new_name']}")
                    print()

        if skipped:
            print(f"Files unchanged: {len(skipped)}")
            if verbose:
                for filename in skipped:
                    print(f"  ✓ {filename} (already in correct format)")

        if errors:
            print(f"Files with errors: {len(errors)}")
            if verbose:
                for error in errors:
                    print(f"  ✗ {error['file']}: {error['error']}")

        # Execute renames
        renamed = 0
        rename_errors = []

        if not dry_run and rename_plan:
            print("\nExecuting renames...")
            print("-" * 60)

            for old_path, info in rename_plan.items():
                try:
                    os.rename(old_path, info['new_path'])
                    renamed += 1
                    if verbose:
                        print(f"  ✓ {info['old_name']} -> {info['new_name']}")
                except Exception as e:
                    rename_errors.append({
                        'file': info['old_name'],
                        'error': str(e)
                    })
                    print(f"  ✗ Failed to rename {info['old_name']}: {e}")

        # Summary
        results = {
            'files_found': len(las_files),
            'to_rename': len(rename_plan),
            'renamed': renamed,
            'skipped': len(skipped),
            'errors': len(errors) + len(rename_errors),
            'dry_run': dry_run,
            'backup_created': self.backup_file if create_backup and not dry_run else None
        }

        return results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Rename LAS files to standardized format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input_dir', help='Directory containing LAS files to rename')
    parser.add_argument('-p', '--pattern', default='*_LLR_L2*.las',
                       help='Glob pattern to match files (default: *_LLR_L2*.las)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--suffix', help='Suffix to add to filenames (e.g., "_orthometric")')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be renamed without actually doing it')
    parser.add_argument('--backup', action='store_true',
                       help='Create backup file with original filenames')

    args = parser.parse_args()

    try:
        # Initialize renamer
        renamer = LASRenamer()

        # Process files
        start_time = datetime.now()
        print(f"Starting LAS file renaming at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Input directory: {args.input_dir}")
        print(f"Pattern: {args.pattern}")

        if args.dry_run:
            print("DRY RUN MODE - No files will be renamed")
        if args.backup:
            print("Backup will be created")
        print("-" * 60)

        results = renamer.rename_files(
            directory=args.input_dir,
            pattern=args.pattern,
            suffix=args.suffix if args.suffix else "",
            verbose=args.verbose,
            dry_run=args.dry_run,
            create_backup=args.backup
        )

        # Summary
        end_time = datetime.now()
        duration = end_time - start_time

        print("\n" + "=" * 60)
        print("RENAMING SUMMARY")
        print("=" * 60)
        print(f"Files found: {results['files_found']}")
        print(f"Files to rename: {results['to_rename']}")
        print(f"Files renamed: {results['renamed']}")
        print(f"Files skipped: {results['skipped']}")
        print(f"Files with errors: {results['errors']}")
        print(f"Duration: {duration}")

        if results.get('backup_created'):
            print(f"Backup file: {results['backup_created']}")

        if args.dry_run:
            print("\nTo perform the actual renaming, run without --dry-run")

        print(f"\nCompleted at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
