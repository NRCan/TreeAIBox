import csv
import sys
import os
from statistics import mean

def calculate_column_averages(csv_file_path):
    """
    Reads a CSV file and calculates the average for each numerical column.
    Skips columns that contain non-numerical data.
    """
    if not os.path.isfile(csv_file_path):
        print(f"Error: File '{csv_file_path}' not found.")
        return

    averages = {}
    with open(csv_file_path, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader, None)  # Read the first row as headers
        if not headers:
            print("Error: CSV file is empty or has no headers.")
            return

        # Initialize lists for each column
        column_data = {header: [] for header in headers}

        for row in reader:
            for i, value in enumerate(row):
                if i < len(headers):
                    try:
                        # Try to convert to float
                        num_value = float(value.strip())
                        # Skip -9999 values as they are likely no-data indicators
                        if num_value == -9999:
                            continue
                        column_data[headers[i]].append(num_value)
                    except ValueError:
                        # Skip non-numerical values
                        pass

        # Calculate averages for columns with numerical data
        for header, values in column_data.items():
            if values:
                try:
                    avg = mean(values)
                    averages[header] = avg
                except:
                    pass  # Skip if mean calculation fails

    return averages

def main():
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = input("Enter the path to the CSV file: ").strip()

    if not csv_file:
        print("No file path provided.")
        return

    print(f"Calculating averages for: {csv_file}")
    averages = calculate_column_averages(csv_file)

    if averages:
        print("\nColumn Averages:")
        for column, avg in averages.items():
            print(f"{column}: {avg:.2f}")
    else:
        print("No numerical columns found or file could not be processed.")

if __name__ == "__main__":
    main()
