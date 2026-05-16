import pandas as pd
import os
import numpy as np
import glob

def calculate_average_metrics_for_all_plots():
    """Calculate average metrics for all plots across all dates"""

    # Base directory containing all date folders
    base_dir = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output"

    # Get all date folders
    date_folders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f)) and f.endswith('_LLR_L2_orthometric')]

    print(f"Found {len(date_folders)} date folders to process")

    total_files_processed = 0

    for date_folder in sorted(date_folders):
        date_path = os.path.join(base_dir, date_folder)
        gridmetrics_path = os.path.join(date_path, 'gridmetrics')

        if not os.path.exists(gridmetrics_path):
            print(f"Skipping {date_folder}: no gridmetrics folder")
            continue

        print(f"\nProcessing {date_folder}...")

        # Create average_metrics folder
        average_metrics_path = os.path.join(gridmetrics_path, 'average_metrics')
        os.makedirs(average_metrics_path, exist_ok=True)

        # Find all elevation stats CSV files for this date
        elevation_csv_pattern = os.path.join(gridmetrics_path, '*_clipped_*_normalized_gridmetrics_all_returns_elevation_stats.csv')
        elevation_csv_files = glob.glob(elevation_csv_pattern)

        print(f"Found {len(elevation_csv_files)} elevation stats CSV files")

        plots_processed = 0

        for csv_file in sorted(elevation_csv_files):
            try:
                # Extract plot number from filename
                filename = os.path.basename(csv_file)
                # Pattern: DATE_clipped_PLOT_normalized_gridmetrics_all_returns_elevation_stats.csv
                plot_match = filename.split('_clipped_')[1].split('_')[0]  # Extract plot number
                plot_number = f"plot_{plot_match}"

                print(f"  Processing {filename} (plot {plot_match})...")

                # Read the CSV file
                df = pd.read_csv(csv_file)

                # Replace -9999 with NaN for proper averaging
                df = df.replace(-9999, np.nan)

                # Calculate averages for all numeric columns
                averages = {}
                for column in df.columns:
                    if column not in ['row', 'col']:  # Skip grid position columns
                        if df[column].dtype in ['int64', 'float64']:
                            # Calculate mean only for non-NaN values
                            mean_val = df[column].mean()
                            if not np.isnan(mean_val):
                                averages[column] = mean_val

                # Create a new dataframe with the averages
                result_df = pd.DataFrame([averages])

                # Create output filename
                output_filename = f"{date_folder}_clipped_{plot_match}_average_metrics.csv"
                output_file = os.path.join(average_metrics_path, output_filename)

                # Save to CSV
                result_df.to_csv(output_file, index=False)

                print(f"    ✓ Saved averages for {len(averages)} metrics to {output_filename}")
                plots_processed += 1
                total_files_processed += 1

            except Exception as e:
                print(f"    ✗ Error processing {filename}: {e}")
                continue

        print(f"  Completed {plots_processed} plots for {date_folder}")

    print(f"\n{'='*50}")
    print(f"SUMMARY: Processed {total_files_processed} files across {len(date_folders)} dates")
    print(f"{'='*50}")

if __name__ == "__main__":
    calculate_average_metrics_for_all_plots()
