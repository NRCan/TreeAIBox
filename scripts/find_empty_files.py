import os

def find_empty_files(root_dir):
    empty_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                if os.path.getsize(file_path) == 0:
                    empty_files.append(file_path)
            except OSError:
                # Skip files that can't be accessed
                pass
    return empty_files

if __name__ == "__main__":
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    empty_files = find_empty_files(workspace_root)
    if empty_files:
        print("Empty files found:")
        for file in empty_files:
            print(file)
        response = input("Do you want to delete all these empty files? (y/n): ").strip().lower()
        if response == 'y':
            for file in empty_files:
                try:
                    os.remove(file)
                    print(f"Deleted: {file}")
                except OSError as e:
                    print(f"Failed to delete {file}: {e}")
    else:
        print("No empty files found.")
