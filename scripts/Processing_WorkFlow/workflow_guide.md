# Guide: Adding New FUSION Tool Workflows in Python

This guide explains how to add new workflow functions for FUSION tools in your Python scripts, following the structure used in `run_fusion_workflow.py`.

## 1. Structure Overview
- **Common parameters** (e.g., `fusion_dir`, `las_file_path`, `output_root`, `overwrite`) are defined at the top of the script.
- **Each workflow function** (e.g., `polyclip`, `groundfilter`) has:
  - Tool-specific parameters as function arguments (with defaults if appropriate)
  - Output folder and file naming logic
  - Executable selection logic (try 64-bit, then 32-bit, error if not found)
  - Command construction (PowerShell style)
  - Optional `print_info` flag for verbosity

## 2. Adding a New Workflow Function
1. **Define the function** in the same style as `polyclip` and `groundfilter`:
   - Accept tool-specific parameters as arguments.
   - Add a `print_info=True` argument for verbosity control.
2. **Select the executable**:
   ```python
   exe_path = os.path.join(fusion_dir, 'ToolName64.exe')
   if not os.path.isfile(exe_path):
       exe_path = os.path.join(fusion_dir, 'ToolName.exe')
   if not os.path.isfile(exe_path):
       print(f'[ERROR] ToolName.exe not found in Fusion folder: {fusion_dir}')
       return
   ```
3. **Prepare output folders/files** as needed for the tool.
4. **Build the command** as a PowerShell string, using all required options and arguments.
5. **Wrap print statements** with `if print_info:` for optional verbosity.
6. **Run the command** with:
   ```python
   result = subprocess.run(['powershell', '-Command', cmd])
   if print_info:
       print('Return code:', result.returncode)
   ```

## 3. Example Template
```python
def new_tool_workflow(param1, param2, print_info=True):
    exe_path = os.path.join(fusion_dir, 'NewTool64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'NewTool.exe')
    if not os.path.isfile(exe_path):
        print(f'[ERROR] NewTool.exe not found in Fusion folder: {fusion_dir}')
        return

    # Prepare output paths as needed
    output_folder = os.path.join(output_root, 'new_tool_output')
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, 'output.las')

    # Build command
    options = []
    # Add tool-specific options here
    options_str = ' '.join(options)
    cmd = f'& "{exe_path}" {options_str} "{param1}" "{param2}" "{output_file}"'

    if print_info:
        print('Running NewTool with the following parameters:')
        # ...print details...
        print(cmd)

    result = subprocess.run(['powershell', '-Command', cmd])
    if print_info:
        print('Return code:', result.returncode)
```

## 4. Calling the Workflow
In the `if __name__ == "__main__":` block, call your new function with the required arguments:
```python
if __name__ == "__main__":
    new_tool_workflow(param1, param2, print_info=True)
```

## 5. Best Practices
- Keep all common parameters at the top of the script.
- Use clear, consistent variable names for output folders/files.
- Always check for the existence of the executable.
- Use the `print_info` flag for all print statements.
- Document tool-specific parameters in the function docstring.

---

For more examples, see the `polyclip` and `groundfilter` functions in `run_fusion_workflow.py`.
