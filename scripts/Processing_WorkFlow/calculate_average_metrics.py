import pandas as pd
import os
import numpy as np

# File paths
input_file = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output\20250407_LLR_L2_orthometric\gridmetrics\20250407_LLR_L2_orthometric_clipped_1_normalized_gridmetrics_all_returns_elevation_stats.csv"
output_dir = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output\20250407_LLR_L2_orthometric\gridmetrics\average_metrics"
output_file = os.path.join(output_dir, "20250407_LLR_L2_orthometric_clipped_1_average_metrics.csv")

# Read the CSV file
df = pd.read_csv(input_file)

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

# Save to CSV
result_df.to_csv(output_file, index=False)

print(f"Average metrics saved to: {output_file}")
print(f"Calculated averages for {len(averages)} metrics")
print("Sample averages:")
for i, (metric, value) in enumerate(list(averages.items())[:10]):
    print(f"  {metric}: {value:.4f}")
