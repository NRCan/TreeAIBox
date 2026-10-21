#!/usr/bin/env python3
"""
LAS File Report Generator using lasinfo

This script generates detailed reports for LAS (LiDAR) files using the lasinfo tool
from LAStools. It can process individual files, directories, or use wildcards.

Usage:
    python lasinfo_report_generator.py [options] <las_file_or_directory>

Options:
    -o, --output DIR        Output directory for reports (default: same as input)
    -f, --format FORMAT     Output format: txt, json, or both (default: txt)
    -r, --recursive         Process directories recursively
    -v, --verbose           Verbose output
    -d, --density           Include point density calculation
    --no-header             Skip header information in reports
    --no-vlrs               Skip variable length records
    --cores NUM             Number of CPU cores to use (default: 1)
    --consolidated-classifications  Generate consolidated classification report
    --classification-output FILE    Output file for consolidated report

Examples:
    # Generate report for single file
    python lasinfo_report_generator.py "Data/Terrestrial/Georeferenced_LAS/merged_plots.las"

    # Generate reports for all LAS files in directory
    python lasinfo_report_generator.py "Data/Terrestrial/Clipped_Plots/"

    # Generate JSON reports with density calculation
    python lasinfo_report_generator.py -f json -d "Data/Terrestrial/*.las"

    # Generate consolidated classification report
    python lasinfo_report_generator.py --consolidated-classifications "Data/Airborne/Input/" --classification-output "reports/classifications.txt"

    # Recursive processing with custom output directory
    python lasinfo_report_generator.py -r -o "reports/" "Data/"
"""

import os
import sys
import glob
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


class LASInfoReporter:
    """Class to handle LAS file reporting using lasinfo tool"""

    def __init__(self, lasinfo_path=None):
        """
        Initialize the reporter with lasinfo executable path

        Args:
            lasinfo_path (str): Path to lasinfo64.exe. If None, will try to find it automatically
        """
        if lasinfo_path is None:
            # Try to find lasinfo in common locations
            possible_paths = [
                r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\LAStools\bin\lasinfo64.exe",
                r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\LAStools\bin\lasinfo.exe",
                "lasinfo64.exe",
                "lasinfo.exe"
            ]

            for path in possible_paths:
                if os.path.isfile(path):
                    lasinfo_path = path
                    break

        if not lasinfo_path or not os.path.isfile(lasinfo_path):
            raise FileNotFoundError(f"lasinfo executable not found. Please specify the path to lasinfo64.exe")

        self.lasinfo_path = lasinfo_path
        print(f"Using lasinfo: {self.lasinfo_path}")

    def generate_report(self, las_file, output_dir=None, format_type='txt',
                       include_density=False, no_header=False, no_vlrs=False,
                       verbose=False):
        """
        Generate a report for a single LAS file

        Args:
            las_file (str): Path to the LAS file
            output_dir (str): Output directory for the report
            format_type (str): Output format ('txt', 'json', or 'both')
            include_density (bool): Include point density calculation
            no_header (bool): Skip header information
            no_vlrs (bool): Skip variable length records
            verbose (bool): Verbose output

        Returns:
            dict: Report generation results
        """
        if not os.path.isfile(las_file):
            return {'success': False, 'error': f'LAS file not found: {las_file}'}

        # Determine output file paths
        las_path = Path(las_file)
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = las_path.parent

        base_name = las_path.stem

        # Build lasinfo command
        cmd = [self.lasinfo_path, '-i', str(las_path)]

        # Add options
        if include_density:
            cmd.append('-compute_density')

        if no_header:
            cmd.append('-no_header')

        if no_vlrs:
            cmd.append('-no_vlrs')

        results = {'las_file': str(las_file), 'reports': []}

        try:
            if format_type in ['txt', 'both']:
                # Generate text report
                txt_output = output_path / f"{base_name}_lasinfo_report.txt"
                txt_cmd = cmd + ['-o', str(txt_output)]

                if verbose:
                    print(f"Generating text report: {txt_output}")

                result = subprocess.run(txt_cmd, capture_output=True, text=True, shell=True)

                if result.returncode == 0:
                    results['reports'].append({
                        'type': 'text',
                        'path': str(txt_output),
                        'success': True
                    })
                    if verbose:
                        print(f"✓ Text report generated: {txt_output}")
                else:
                    results['reports'].append({
                        'type': 'text',
                        'path': str(txt_output),
                        'success': False,
                        'error': result.stderr
                    })
                    print(f"✗ Failed to generate text report: {result.stderr}")

            if format_type in ['json', 'both']:
                # Generate JSON report
                json_output = output_path / f"{base_name}_lasinfo_report.json"
                json_cmd = cmd + ['-ojs', '-o', str(json_output)]

                if verbose:
                    print(f"Generating JSON report: {json_output}")

                result = subprocess.run(json_cmd, capture_output=True, text=True, shell=True)

                if result.returncode == 0:
                    results['reports'].append({
                        'type': 'json',
                        'path': str(json_output),
                        'success': True
                    })
                    if verbose:
                        print(f"✓ JSON report generated: {json_output}")
                else:
                    results['reports'].append({
                        'type': 'json',
                        'path': str(json_output),
                        'success': False,
                        'error': result.stderr
                    })
                    print(f"✗ Failed to generate JSON report: {result.stderr}")

            results['success'] = any(report['success'] for report in results['reports'])

        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"✗ Error processing {las_file}: {e}")

    def extract_classifications(self, las_file, verbose=False):
        """
        Extract classification information from a LAS file

        Args:
            las_file (str): Path to the LAS file
            verbose (bool): Verbose output

        Returns:
            dict: Classification data for the file
        """
        if not os.path.isfile(las_file):
            return {'success': False, 'error': f'LAS file not found: {las_file}'}

        # Run lasinfo to get classification data
        cmd = [self.lasinfo_path, '-i', str(las_file), '-stdout']

        if verbose:
            print(f"Extracting classifications from: {Path(las_file).name}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)

            if result.returncode != 0:
                return {
                    'success': False,
                    'file': str(las_file),
                    'error': result.stderr
                }

            # Parse the output to extract classification histogram
            output_lines = result.stdout.split('\n')
            classifications = {}
            in_histogram = False

            for line in output_lines:
                line = line.strip()
                if 'histogram of classification of points:' in line.lower():
                    in_histogram = True
                    continue
                elif in_histogram and line.startswith('histogram of'):
                    # We've moved to another histogram section
                    break
                elif in_histogram and line:
                    # Parse classification line: "count  description (class_number)"
                    try:
                        parts = line.split()
                        if len(parts) >= 3:
                            count = int(parts[0].replace(',', ''))
                            # Extract class number from parentheses
                            class_part = parts[-1]
                            if class_part.startswith('(') and class_part.endswith(')'):
                                class_num = int(class_part[1:-1])
                                # Extract description (everything between count and class number)
                                desc_parts = parts[1:-1]
                                description = ' '.join(desc_parts)

                                classifications[class_num] = {
                                    'description': description,
                                    'count': count
                                }
                    except (ValueError, IndexError):
                        continue

            return {
                'success': True,
                'file': str(las_file),
                'filename': Path(las_file).name,
                'classifications': classifications
            }

        except Exception as e:
            return {
                'success': False,
                'file': str(las_file),
                'error': str(e)
            }

    def generate_consolidated_classification_report(self, input_path, output_file,
                                                  recursive=False, verbose=False):
        """
        Generate a consolidated report of all classifications across multiple LAS files

        Args:
            input_path (str): Input path (directory or wildcard pattern)
            output_file (str): Output file path for the consolidated report
            recursive (bool): Process directories recursively
            verbose (bool): Verbose output

        Returns:
            dict: Report generation results
        """
        input_path = Path(input_path)

        # Find all LAS files
        if input_path.is_dir():
            if recursive:
                las_files = list(input_path.rglob("*.las"))
            else:
                las_files = list(input_path.glob("*.las"))
            las_files = [str(f) for f in las_files]
        else:
            # Treat as wildcard pattern
            las_files = glob.glob(str(input_path))
            las_files = [f for f in las_files if f.lower().endswith('.las')]

        if not las_files:
            print(f"No LAS files found at: {input_path}")
            return {'success': False, 'error': 'No LAS files found'}

        print(f"Found {len(las_files)} LAS file(s) to analyze for classifications")

        # Extract classifications from all files
        all_classifications = {}
        file_results = []

        for i, las_file in enumerate(las_files, 1):
            if verbose:
                print(f"\n[{i}/{len(las_files)}] Analyzing: {Path(las_file).name}")
            else:
                print(f"Analyzing {i}/{len(las_files)}: {Path(las_file).name}")

            result = self.extract_classifications(las_file, verbose)
            file_results.append(result)

            if result['success']:
                # Merge classifications
                for class_num, class_data in result['classifications'].items():
                    if class_num not in all_classifications:
                        all_classifications[class_num] = {
                            'description': class_data['description'],
                            'files': [],
                            'total_count': 0
                        }

                    all_classifications[class_num]['files'].append({
                        'filename': result['filename'],
                        'count': class_data['count']
                    })
                    all_classifications[class_num]['total_count'] += class_data['count']

        # Generate consolidated report
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                # Write header
                f.write("=" * 80 + "\n")
                f.write("CONSOLIDATED LAS CLASSIFICATION REPORT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Input directory: {input_path}\n")
                f.write(f"Files analyzed: {len([r for r in file_results if r['success']])}\n")
                f.write(f"Files with errors: {len([r for r in file_results if not r['success']])}\n")
                f.write("\n")

                # Write summary of all classifications found
                f.write("ALL CLASSIFICATIONS FOUND:\n")
                f.write("-" * 80 + "\n")
                f.write(f"{'Class':<8} {'Description':<25} {'Total Count':<15} {'Files':<8}\n")
                f.write("-" * 80 + "\n")

                # Sort classifications by class number
                for class_num in sorted(all_classifications.keys()):
                    class_data = all_classifications[class_num]
                    f.write(f"{class_num:<8} {class_data['description']:<25} {class_data['total_count']:<15,} {len(class_data['files']):<8}\n")

                f.write("\n\n")

                # Write detailed breakdown by file
                f.write("DETAILED BREAKDOWN BY FILE:\n")
                f.write("-" * 80 + "\n")

                for result in file_results:
                    if result['success']:
                        f.write(f"\nFile: {result['filename']}\n")
                        f.write("-" * 40 + "\n")

                        if result['classifications']:
                            for class_num in sorted(result['classifications'].keys()):
                                class_data = result['classifications'][class_num]
                                f.write(f"  {class_num:<8} {class_data['description']:<25} {class_data['count']:<15,}\n")
                        else:
                            f.write("  No classifications found\n")

                # Write error summary if any
                failed_files = [r for r in file_results if not r['success']]
                if failed_files:
                    f.write("\n\nFILES WITH ERRORS:\n")
                    f.write("-" * 80 + "\n")
                    for failed in failed_files:
                        f.write(f"File: {failed.get('filename', failed.get('file', 'Unknown'))}\n")
                        f.write(f"Error: {failed.get('error', 'Unknown error')}\n\n")

            print(f"\n✓ Consolidated classification report saved to: {output_file}")

            return {
                'success': True,
                'output_file': str(output_file),
                'files_analyzed': len([r for r in file_results if r['success']]),
                'files_failed': len([r for r in file_results if not r['success']]),
                'total_classifications': len(all_classifications),
                'classifications': all_classifications
            }

        except Exception as e:
            error_msg = f"Error generating consolidated report: {e}"
            print(f"✗ {error_msg}")
            return {'success': False, 'error': error_msg}

    def process_files(self, input_path, output_dir=None, format_type='txt',
                     recursive=False, include_density=False, no_header=False,
                     no_vlrs=False, cores=1, verbose=False):
        """
        Process multiple LAS files

        Args:
            input_path (str): Input path (file, directory, or wildcard pattern)
            output_dir (str): Output directory for reports
            format_type (str): Output format
            recursive (bool): Process directories recursively
            include_density (bool): Include point density calculation
            no_header (bool): Skip header information
            no_vlrs (bool): Skip variable length records
            cores (int): Number of CPU cores to use
            verbose (bool): Verbose output

        Returns:
            list: List of processing results
        """
        input_path = Path(input_path)

        # Find all LAS files
        if input_path.is_file():
            las_files = [str(input_path)]
        elif input_path.is_dir():
            if recursive:
                las_files = list(input_path.rglob("*.las"))
            else:
                las_files = list(input_path.glob("*.las"))
            las_files = [str(f) for f in las_files]
        else:
            # Treat as wildcard pattern
            las_files = glob.glob(str(input_path))
            las_files = [f for f in las_files if f.lower().endswith('.las')]

        if not las_files:
            print(f"No LAS files found at: {input_path}")
            return []

        print(f"Found {len(las_files)} LAS file(s) to process")

        results = []
        for i, las_file in enumerate(las_files, 1):
            if verbose:
                print(f"\n[{i}/{len(las_files)}] Processing: {Path(las_file).name}")
            else:
                print(f"Processing {i}/{len(las_files)}: {Path(las_file).name}")

            result = self.generate_report(
                las_file=las_file,
                output_dir=output_dir,
                format_type=format_type,
                include_density=include_density,
                no_header=no_header,
                no_vlrs=no_vlrs,
                verbose=verbose
            )
            results.append(result)

        return results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Generate LAS file reports using lasinfo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input', help='LAS file, directory, or wildcard pattern')
    parser.add_argument('-o', '--output', help='Output directory for reports')
    parser.add_argument('-f', '--format', choices=['txt', 'json', 'both'],
                       default='txt', help='Output format (default: txt)')
    parser.add_argument('-r', '--recursive', action='store_true',
                       help='Process directories recursively')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-d', '--density', action='store_true',
                       help='Include point density calculation')
    parser.add_argument('--no-header', action='store_true',
                       help='Skip header information in reports')
    parser.add_argument('--no-vlrs', action='store_true',
                       help='Skip variable length records')
    parser.add_argument('--cores', type=int, default=1,
                       help='Number of CPU cores to use (default: 1)')
    parser.add_argument('--consolidated-classifications', action='store_true',
                       help='Generate a consolidated report of all classifications across files')
    parser.add_argument('--classification-output', help='Output file for consolidated classification report')
    parser.add_argument('--lasinfo-path', help='Path to lasinfo64.exe')

    args = parser.parse_args()

    try:
        # Initialize reporter
        reporter = LASInfoReporter(lasinfo_path=args.lasinfo_path)

        # Handle consolidated classification report
        if args.consolidated_classifications:
            if not args.classification_output:
                args.classification_output = "consolidated_classifications_report.txt"

            print(f"Generating consolidated classification report...")
            print(f"Input: {args.input}")
            print(f"Output: {args.classification_output}")
            print("-" * 50)

            result = reporter.generate_consolidated_classification_report(
                input_path=args.input,
                output_file=args.classification_output,
                recursive=args.recursive,
                verbose=args.verbose
            )

            if result['success']:
                print("\n" + "=" * 50)
                print("CONSOLIDATED CLASSIFICATION REPORT SUMMARY")
                print("=" * 50)
                print(f"Files analyzed: {result['files_analyzed']}")
                print(f"Files with errors: {result['files_failed']}")
                print(f"Total unique classifications found: {result['total_classifications']}")
                print(f"Report saved to: {result['output_file']}")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

            return

        # Process files
        start_time = datetime.now()
        print(f"Starting LAS report generation at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Input: {args.input}")
        print(f"Output format: {args.format}")
        if args.output:
            print(f"Output directory: {args.output}")
        print("-" * 50)

        results = reporter.process_files(
            input_path=args.input,
            output_dir=args.output,
            format_type=args.format,
            recursive=args.recursive,
            include_density=args.density,
            no_header=args.no_header,
            no_vlrs=args.no_vlrs,
            cores=args.cores,
            verbose=args.verbose
        )

        # Summary
        end_time = datetime.now()
        duration = end_time - start_time

        successful = sum(1 for r in results if r['success'])
        total_reports = sum(len(r['reports']) for r in results)

        print("\n" + "=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"Files processed: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(results) - successful}")
        print(f"Total reports generated: {total_reports}")
        print(f"Duration: {duration}")
        print(f"Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if results:
            print("\nReport files generated:")
            for result in results:
                if result['success']:
                    for report in result['reports']:
                        if report['success']:
                            print(f"  ✓ {report['path']}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
