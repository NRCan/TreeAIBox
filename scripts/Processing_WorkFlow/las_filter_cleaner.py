#!/usr/bin/env python3
"""
LAS File Filter and Cleaner

This script filters LAS files to remove noise and overlap classifications,
then saves the cleaned files to a processed_las directory.

Usage:
    python las_filter_cleaner.py [options] <input_directory> <classification_report>

Options:
    -o, --output DIR        Output directory for processed files (default: input_dir/processed_las)
    -c, --classes CLASSES   Classification numbers to remove (default: 7,12 for noise and overlap)
    -v, --verbose           Verbose output
    --lastools-path DIR     Path to LAStools bin directory
    --dry-run               Show what would be done without actually processing files

Examples:
    # Filter noise and overlap from all LAS files
    python las_filter_cleaner.py "Data/Airborne/Input/" "reports/raw_classifications_report.txt"

    # Filter only specific classifications
    python las_filter_cleaner.py -c "7 12 18" "Data/Airborne/Input/" "reports/raw_classifications_report.txt"

    # Dry run to see what would be processed
    python las_filter_cleaner.py --dry-run "Data/Airborne/Input/" "reports/raw_classifications_report.txt"
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


class LASFilterCleaner:
    """Class to handle LAS file filtering and cleaning"""

    def __init__(self, lastools_path=None):
        """
        Initialize the cleaner with LAStools path

        Args:
            lastools_path (str): Path to LAStools bin directory. If None, will try to find it automatically
        """
        if lastools_path is None:
            # Try to find LAStools in common locations
            possible_paths = [
                r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\LAStools\bin",
                r"C:\LAStools\bin",
                "LAStools\bin"
            ]

            for path in possible_paths:
                if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'las2las64.exe')):
                    lastools_path = path
                    break

        if not lastools_path or not os.path.isdir(lastools_path):
            raise FileNotFoundError(f"LAStools bin directory not found. Please specify the path to LAStools\bin")

        self.lastools_path = Path(lastools_path)
        self.las2las_path = self.lastools_path / 'las2las64.exe'

        if not self.las2las_path.exists():
            # Try without 64 suffix
            self.las2las_path = self.lastools_path / 'las2las.exe'
            if not self.las2las_path.exists():
                raise FileNotFoundError(f"las2las executable not found in {lastools_path}")

        print(f"Using LAStools: {self.lastools_path}")
        print(f"Using las2las: {self.las2las_path}")

    def parse_classification_report(self, report_file):
        """
        Parse the classification report to identify files that need filtering

        Args:
            report_file (str): Path to the classification report file

        Returns:
            dict: Dictionary with file information and classifications to filter
        """
        files_to_process = {}

        try:
            with open(report_file, 'r') as f:
                content = f.read()

            # Split by file sections
            file_sections = content.split('File: ')

            for section in file_sections[1:]:  # Skip the first empty section
                lines = section.strip().split('\n')
                if not lines:
                    continue

                # Extract filename
                filename = lines[0].strip()
                if not filename.endswith('.las'):
                    continue

                # Parse classifications for this file
                classifications = {}
                for line in lines[2:]:  # Skip filename and separator
                    line = line.strip()
                    if not line or line.startswith('-'):
                        continue

                    try:
                        parts = line.split()
                        if len(parts) >= 3:
                            class_num = int(parts[0])
                            # Remove commas from count
                            count = int(parts[-1].replace(',', ''))
                            # Description is everything in between
                            description = ' '.join(parts[1:-1])
                            classifications[class_num] = {
                                'description': description,
                                'count': count
                            }
                    except (ValueError, IndexError):
                        continue

                if classifications:
                    files_to_process[filename] = classifications

        except Exception as e:
            print(f"Error parsing classification report: {e}")
            return {}

        return files_to_process

    def filter_las_file(self, input_file, output_file, classes_to_remove, verbose=False, dry_run=False):
        """
        Filter a single LAS file by removing specified classifications

        Args:
            input_file (str): Path to input LAS file
            output_file (str): Path to output LAS file
            classes_to_remove (list): List of classification numbers to remove
            verbose (bool): Verbose output
            dry_run (bool): Show what would be done without actually processing

        Returns:
            dict: Processing results
        """
        if not os.path.isfile(input_file):
            return {'success': False, 'error': f'Input file not found: {input_file}'}

        # Build las2las command
        cmd = [
            str(self.las2las_path),
            '-i', str(input_file),
            '-o', str(output_file)
        ]

        # Add drop classification options
        for class_num in classes_to_remove:
            cmd.extend(['-drop_classification', str(class_num)])

        if verbose or dry_run:
            print(f"Command: {' '.join(cmd)}")

        if dry_run:
            return {'success': True, 'dry_run': True, 'command': ' '.join(cmd)}

        try:
            # Ensure output directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if verbose:
                print(f"Filtering {Path(input_file).name} -> {output_path.name}")

            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)

            if result.returncode == 0:
                # Check if output file was created and get its size
                if output_path.exists():
                    output_size = output_path.stat().st_size
                    input_size = Path(input_file).stat().st_size

                    return {
                        'success': True,
                        'input_file': str(input_file),
                        'output_file': str(output_file),
                        'input_size': input_size,
                        'output_size': output_size,
                        'size_reduction': input_size - output_size
                    }
                else:
                    return {'success': False, 'error': 'Output file was not created'}
            else:
                return {
                    'success': False,
                    'error': result.stderr,
                    'command': ' '.join(cmd)
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'command': ' '.join(cmd)
            }

    def process_files(self, input_dir, classification_report, output_dir=None,
                     classes_to_remove=None, verbose=False, dry_run=False):
        """
        Process all LAS files that need filtering based on the classification report

        Args:
            input_dir (str): Input directory containing LAS files
            classification_report (str): Path to classification report
            output_dir (str): Output directory for processed files
            classes_to_remove (list): List of classification numbers to remove
            verbose (bool): Verbose output
            dry_run (bool): Show what would be done without actually processing

        Returns:
            list: List of processing results
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        # Set default classes to remove if not specified
        if classes_to_remove is None:
            classes_to_remove = [7, 12]  # noise and overlap

        # Set default output directory
        if output_dir is None:
            output_dir = input_path / "processed_las"

        output_path = Path(output_dir)

        # Parse classification report
        print(f"Parsing classification report: {classification_report}")
        files_to_process = self.parse_classification_report(classification_report)

        if not files_to_process:
            print("No files found in classification report")
            return []

        print(f"Found {len(files_to_process)} files in classification report")

        # Filter to only files that actually exist and have the classes we want to remove
        files_to_filter = {}
        for filename, classifications in files_to_process.items():
            input_file = input_path / filename
            if input_file.exists():
                # Check if file has any of the classes we want to remove
                has_classes_to_remove = any(cls in classifications for cls in classes_to_remove)
                if has_classes_to_remove:
                    files_to_filter[filename] = classifications
                elif verbose:
                    print(f"Skipping {filename} - no target classifications found")
            else:
                print(f"Warning: {filename} not found in input directory")

        if not files_to_filter:
            print("No files need filtering based on the specified classifications")
            return []

        print(f"Will process {len(files_to_filter)} files")
        print(f"Removing classifications: {', '.join(map(str, classes_to_remove))}")
        print(f"Output directory: {output_path}")
        print("-" * 60)

        results = []
        total_input_size = 0
        total_output_size = 0

        for filename, classifications in files_to_filter.items():
            input_file = input_path / filename
            output_file = output_path / filename

            if verbose:
                print(f"\nProcessing: {filename}")
                print(f"  Classifications: {list(classifications.keys())}")

            result = self.filter_las_file(
                input_file=str(input_file),
                output_file=str(output_file),
                classes_to_remove=classes_to_remove,
                verbose=verbose,
                dry_run=dry_run
            )

            results.append(result)

            if result['success'] and not dry_run:
                total_input_size += result.get('input_size', 0)
                total_output_size += result.get('output_size', 0)

                if verbose:
                    reduction = result.get('size_reduction', 0)
                    print(f"  Size reduction: {reduction:,} bytes")

        return results, total_input_size, total_output_size


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Filter and clean LAS files by removing unwanted classifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input_dir', help='Input directory containing LAS files')
    parser.add_argument('classification_report', help='Path to classification report file')
    parser.add_argument('-o', '--output', help='Output directory for processed files')
    parser.add_argument('-c', '--classes', help='Classification numbers to remove (space-separated)',
                       default='7 12')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually processing files')
    parser.add_argument('--lastools-path', help='Path to LAStools bin directory')

    args = parser.parse_args()

    try:
        # Initialize cleaner
        cleaner = LASFilterCleaner(lastools_path=args.lastools_path)

        # Parse classes to remove
        try:
            classes_to_remove = [int(x.strip()) for x in args.classes.split()]
        except ValueError:
            print(f"Error: Invalid classification numbers: {args.classes}")
            sys.exit(1)

        # Process files
        start_time = datetime.now()
        print(f"Starting LAS file filtering at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Input directory: {args.input_dir}")
        print(f"Classification report: {args.classification_report}")
        print(f"Removing classifications: {classes_to_remove}")
        if args.dry_run:
            print("DRY RUN MODE - No files will be modified")
        print("-" * 60)

        results, total_input_size, total_output_size = cleaner.process_files(
            input_dir=args.input_dir,
            classification_report=args.classification_report,
            output_dir=args.output,
            classes_to_remove=classes_to_remove,
            verbose=args.verbose,
            dry_run=args.dry_run
        )

        # Summary
        end_time = datetime.now()
        duration = end_time - start_time

        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful

        print("\n" + "=" * 60)
        print("FILTERING SUMMARY")
        print("=" * 60)
        print(f"Files processed: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Duration: {duration}")

        if not args.dry_run and results:
            size_reduction = total_input_size - total_output_size
            reduction_percent = (size_reduction / total_input_size * 100) if total_input_size > 0 else 0
            print(f"Total input size: {total_input_size:,} bytes")
            print(f"Total output size: {total_output_size:,} bytes")
            print(f"Total size reduction: {size_reduction:,} bytes ({reduction_percent:.1f}%)")

        if failed > 0:
            print("\nFailed files:")
            for result in results:
                if not result['success']:
                    print(f"  ✗ {Path(result.get('input_file', 'Unknown')).name}: {result.get('error', 'Unknown error')}")

        print(f"\nCompleted at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
