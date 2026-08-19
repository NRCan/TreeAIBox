import os
import re
import subprocess

# Directory containing LAS files
output_dir = os.path.join('LLY', 'Output')

# Pattern to match floating-point LAS files
float_pattern = re.compile(r'stand_\d+\.\d+\.las$')

# Get all LAS files in the output directory
las_files = [f for f in os.listdir(output_dir) if f.endswith('.las')]

# Filter files with floating-point suffixes
float_files = [f for f in las_files if float_pattern.match(f)]

# Rename files to sequential integer-based names
for idx, fname in enumerate(float_files, start=1):
    new_name = f'stand_{idx}.las'
    src = os.path.join(output_dir, fname)
    dst = os.path.join(output_dir, new_name)
    print(f'Renaming {fname} to {new_name}')
    os.rename(src, dst)

# Call the batch script for normalization
bat_path = os.path.join('Data', 'normalize_stands.bat')
print('Calling normalization batch script...')
subprocess.run([bat_path], shell=True, check=True)

print('All files renamed and normalized.')
