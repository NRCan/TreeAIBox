import sys
import os
import json
import traceback
import requests
from pathlib import Path
import numpy as np
import torch

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, pyqtSignal, QByteArray, QThread, QEventLoop
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QDesktopServices, QClipboard
from PyQt6.QtWidgets import QMessageBox

# pip install PyQt6, PyQt6-WebEngine

# Import PyCC if available
try:
    import pycc
    import cccorelib

    CC = pycc.GetInstance()
    PYCC_AVAILABLE = True
    print("✓ CloudCompare API loaded successfully")
except ImportError as e:
    PYCC_AVAILABLE = False
    print(f"Warning: PyCC not available. Some functionality will be limited.")
    print(f"Import error details: {e}")
except Exception as e:
    PYCC_AVAILABLE = False
    print(f"Warning: PyCC failed to initialize: {e}")


# Add this helper class to process events during long operations
class ProcessEvents:
    def __init__(self, msec=100):
        self.msec = msec
        self.last_time = 0

    def __call__(self, progress):
        # Process events periodically to keep UI responsive
        import time
        current_time = time.time() * 1000  # Convert to milliseconds
        if current_time - self.last_time > self.msec:
            QApplication.instance().processEvents()
            self.last_time = current_time
        return progress


# Add this worker class to run time-consuming tasks in the background
class Worker(QThread):
    progressUpdated = pyqtSignal(int)
    finished = pyqtSignal(bool, object)
    errorOccurred = pyqtSignal(str)

    def __init__(self, task_function, *args, **kwargs):
        super().__init__()
        self.task_function = task_function
        self.args = args
        self.kwargs = kwargs
        self.result = None

    def run(self):
        try:
            # Replace the progress_callback with our thread-safe version
            if 'progress_callback' in self.kwargs:
                original_callback = self.kwargs['progress_callback']

                def thread_safe_callback(progress):
                    self.progressUpdated.emit(progress)
                    return original_callback(progress)

                self.kwargs['progress_callback'] = thread_safe_callback

            # Execute the task
            self.result = self.task_function(*self.args, **self.kwargs)
            self.finished.emit(True, self.result)
        except Exception as e:
            self.errorOccurred.emit(str(e))
            self.finished.emit(False, None)

class WebEnginePage(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

    def createWindow(self, _):
        return self


class WebInterface(QObject):
    # Signals for communication with JS
    progressUpdated = pyqtSignal(int)
    showNotification = pyqtSignal(str, str)
    updateModelList = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize paths
        self.model_local_path = self.get_model_storage_dir()
        self.log_local_path = self.get_log_storage_dir()
        self.current_directory = os.path.dirname(os.path.realpath(__file__))

        # Load model names
        self.model_json_path = os.path.join(self.current_directory, "model_zoo.json")
        if not os.path.exists(self.model_json_path):
            # Create an empty model list if the file doesn't exist
            with open(self.model_json_path, 'w') as f:
                json.dump([], f)

        with open(self.model_json_path, 'r') as f:
            self.model_names = json.load(f)

        # Server path for models
        # self.model_server_path = "http://xizhouxin.com/static/treeaibox/"
        # self.model_server_path = "https://github.com/truebelief/TreeAIBox/releases/download/v1.0/"
        self.model_server_path = "https://github.com/NRCan/TreeAIBox/releases/download/v1.0/"

        # Check CUDA availability
        self.is_cuda_available = torch.cuda.is_available()

        # Variable to store the selected model
        self.selected_model = ""

        # Add all modules path to system path
        sys.path.append(self.current_directory)

        # Create a process events helper
        self.process_events = ProcessEvents()

        # Keep track of worker threads
        self.workers = []
        
        # Cache for standalone point cloud to persist across processing steps
        self.standalone_point_cloud = None

    def cleanup(self):
        """Clean up resources"""
        for worker in self.workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait(3000)
        self.workers.clear()
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()

    def get_model_storage_dir(self):
        """Create and return the model storage directory path"""
        if os.name == 'nt':  # Windows
            appdata_dir = Path(os.getenv('LOCALAPPDATA'))
        else:  # macOS, Linux, etc.
            appdata_dir = Path.home() / '.local' / 'share'

        model_dir = appdata_dir / 'CloudCompare' / 'TreeAIBox' / 'models'
        model_dir.mkdir(parents=True, exist_ok=True)
        return str(model_dir)

    def get_log_storage_dir(self):
        """Create and return the log storage directory path"""
        if os.name == 'nt':  # Windows
            appdata_dir = Path(os.getenv('LOCALAPPDATA'))
        else:  # macOS, Linux, etc.
            appdata_dir = Path.home() / '.local' / 'share'

        log_dir = appdata_dir / 'CloudCompare' / 'TreeAIBox' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir)

    def checkSelection(self):
        if not PYCC_AVAILABLE:
            # In standalone mode, we'll use file input instead of CloudCompare selection
            if not hasattr(self, 'standalone_file_path') or not self.standalone_file_path:
                self.showNotification.emit("Please select a point cloud file using the '📁 Select Point Cloud' button", "warning")
                return False
            return True
        if not CC.haveSelection():
            self.showNotification.emit("Please select at least one point cloud to proceed", "warning")
            return False
        return True

    def loadStandalonePointCloud(self):
        """Load point cloud from standalone file path, reading scalar fields from LAS extra dimensions"""
        if not hasattr(self, 'standalone_file_path') or not self.standalone_file_path:
            return None
        
        # Don't use cache - always reload from file to get latest scalar fields
        file_ext = os.path.splitext(self.standalone_file_path)[1].lower()
        
        try:
            scalar_fields_to_load = {}
            
            if file_ext in ['.txt', '.xyz', '.pts']:
                # Load ASCII point cloud
                pcd = np.loadtxt(self.standalone_file_path)
            elif file_ext == '.npy':
                # Load numpy binary
                pcd = np.load(self.standalone_file_path)
            elif file_ext in ['.las', '.laz']:
                # Load LAS/LAZ file with scalar fields
                try:
                    import laspy
                    las = laspy.read(self.standalone_file_path)
                    pcd = np.vstack([las.x, las.y, las.z]).T
                    
                    # Load RGB channels if available
                    if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                        scalar_fields_to_load['red'] = np.array(las.red)
                        scalar_fields_to_load['green'] = np.array(las.green)
                        scalar_fields_to_load['blue'] = np.array(las.blue)
                        print(f"Loaded RGB channels from LAS file")
                    
                    # Load extra dimensions as scalar fields
                    for dim_name in las.point_format.extra_dimension_names:
                        try:
                            scalar_fields_to_load[dim_name] = np.array(getattr(las, dim_name))
                            print(f"Loaded scalar field: {dim_name}")
                        except Exception as e:
                            print(f"Warning: Could not load extra dimension {dim_name}: {e}")
                    
                except ImportError:
                    self.showNotification.emit("laspy library required for LAS/LAZ files. Install with: pip install laspy", "error")
                    return None
            else:
                self.showNotification.emit(f"Unsupported file format: {file_ext}", "error")
                return None
            
            # Create a simple point cloud wrapper for standalone mode
            class StandalonePointCloud:
                def __init__(self, points, name, file_path, scalar_fields=None):
                    self._points = points
                    self._name = name
                    self._file_path = file_path
                    self._scalar_fields = scalar_fields if scalar_fields else {}
                    
                def points(self):
                    return self._points
                
                def getName(self):
                    return self._name
                
                def addScalarField(self, name):
                    if name not in self._scalar_fields:
                        self._scalar_fields[name] = np.zeros(len(self._points))
                    return list(self._scalar_fields.keys()).index(name)
                
                def getScalarFieldIndexByName(self, name):
                    if name in self._scalar_fields:
                        return list(self._scalar_fields.keys()).index(name)
                    return -1
                
                def getScalarField(self, index):
                    if isinstance(index, int):
                        name = list(self._scalar_fields.keys())[index]
                    else:
                        name = index
                    
                    class ScalarField:
                        def __init__(self, data):
                            self.data = data
                        def asArray(self):
                            return self.data
                        def computeMinAndMax(self):
                            pass
                    return ScalarField(self._scalar_fields[name])
                
                def setCurrentDisplayedScalarField(self, index):
                    pass
                
                def showSF(self, show):
                    pass
            
            pc = StandalonePointCloud(
                pcd, 
                os.path.basename(self.standalone_file_path), 
                self.standalone_file_path,
                scalar_fields_to_load
            )
            result = [pc]
            
            # Cache the point cloud for future use
            self.standalone_point_cloud = result
            
            return result
            
        except Exception as e:
            self.showNotification.emit(f"Error loading point cloud: {str(e)}", "error")
            import traceback
            traceback.print_exc()
            return None
            return None

    def saveStandaloneResults(self, step_name="results"):
        """Save the current point cloud with all scalar fields to LAS file"""
        if self.standalone_point_cloud is None or len(self.standalone_point_cloud) == 0:
            return None
        
        # Skip LAS save for treeloc step (only TXT file is saved separately)
        if step_name == "treeloc":
            print(f"Skipping LAS save for treeloc step (tree locations saved as TXT)")
            return None
        
        try:
            pc = self.standalone_point_cloud[0]
            
            # Use input file directory as output directory
            if hasattr(pc, '_file_path') and pc._file_path:
                output_dir = os.path.dirname(pc._file_path)
            else:
                output_dir = os.path.join(self.log_local_path, "processed_results")
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename (no timestamp, use step name)
            base_name = os.path.splitext(os.path.basename(pc._name))[0]
            # Remove existing step suffix if present (e.g., _stemcls, _treeloc)
            for suffix in ['_stemcls', '_treeloc', '_treeoff', '_crownoff', '_stemoff']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            output_file = os.path.join(output_dir, f"{base_name}_{step_name}.las")
            
            # Save as LAS file with scalar fields
            try:
                import laspy
                
                # Create LAS file
                header = laspy.LasHeader(point_format=3, version="1.4")
                header.offsets = np.min(pc._points, axis=0)
                header.scales = np.array([0.001, 0.001, 0.001])  # 1mm precision
                
                las = laspy.LasData(header)
                
                # Set coordinates
                las.x = pc._points[:, 0]
                las.y = pc._points[:, 1]
                las.z = pc._points[:, 2]
                
                # Add RGB channels if available in original data
                if 'red' in pc._scalar_fields and 'green' in pc._scalar_fields and 'blue' in pc._scalar_fields:
                    try:
                        las.red = pc._scalar_fields['red'].astype(np.uint16)
                        las.green = pc._scalar_fields['green'].astype(np.uint16)
                        las.blue = pc._scalar_fields['blue'].astype(np.uint16)
                        print(f"Preserved RGB channels in output file")
                    except Exception as e:
                        print(f"Warning: Could not preserve RGB channels: {e}")
                
                # Add scalar fields as extra dimensions
                for field_name, field_data in pc._scalar_fields.items():
                    # Skip RGB channels (already added above)
                    if field_name in ['red', 'green', 'blue']:
                        continue
                    try:
                        # Determine appropriate data type based on field name and content
                        if field_name in ['itc', 'stemcls', 'stemoff', 'treeloc']:
                            # Integer fields for classification/IDs
                            dtype = np.int32
                        else:
                            dtype = np.float32
                        
                        # Add as extra dimension
                        las.add_extra_dim(laspy.ExtraBytesParams(
                            name=field_name,
                            type=dtype
                        ))
                        setattr(las, field_name, field_data.astype(dtype))
                        print(f"[Save] Added scalar field '{field_name}' as {dtype.__name__}")
                    except Exception as e:
                        print(f"Warning: Could not add scalar field {field_name}: {e}")
                
                # Write LAS file
                las.write(output_file)
                
                # Update the cached point cloud to point to the new file
                pc._file_path = output_file
                pc._name = os.path.basename(output_file)
                self.standalone_file_path = output_file
                
                self.showNotification.emit(f"Results saved to: {os.path.basename(output_file)}", "success")
                print(f"Saved results to: {output_file}")
                
                return output_file
                
            except ImportError:
                # Fallback to NPZ if laspy not available
                print("Warning: laspy not available, saving as NPZ instead")
                output_file = os.path.join(output_dir, f"{base_name}_{step_name}.npz")
                
                save_data = {
                    'points': pc._points,
                    'name': pc._name
                }
                
                for field_name, field_data in pc._scalar_fields.items():
                    save_data[f'field_{field_name}'] = field_data
                
                np.savez_compressed(output_file, **save_data)
                
                self.showNotification.emit(f"Results saved to NPZ: {os.path.basename(output_file)}", "success")
                print(f"Saved results to: {output_file}")
                
                return output_file
            
        except Exception as e:
            self.showNotification.emit(f"Error saving results: {str(e)}", "error")
            import traceback
            traceback.print_exc()
            import traceback
            traceback.print_exc()
            return None

    def exportStandaloneResults(self, format_type="txt"):
        """Export results to various formats (txt, csv, las)"""
        if self.standalone_point_cloud is None or len(self.standalone_point_cloud) == 0:
            self.showNotification.emit("No point cloud data to export", "warning")
            return None
        
        try:
            pc = self.standalone_point_cloud[0]
            
            # Use input file directory as output directory
            if hasattr(pc, '_file_path') and pc._file_path:
                output_dir = os.path.dirname(pc._file_path)
            else:
                output_dir = os.path.join(self.log_local_path, "exported_results")
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(pc._name))[0]
            
            if format_type == "txt" or format_type == "xyz":
                # Export as ASCII text file with all columns
                output_file = os.path.join(output_dir, f"{base_name}_exported_{timestamp}.txt")
                
                # Combine points and scalar fields
                data_to_save = [pc._points]
                header = "X Y Z"
                
                for field_name, field_data in pc._scalar_fields.items():
                    data_to_save.append(field_data.reshape(-1, 1))
                    header += f" {field_name}"
                
                combined_data = np.hstack(data_to_save)
                np.savetxt(output_file, combined_data, fmt='%.6f', header=header, comments='')
                
            elif format_type == "csv":
                # Export as CSV
                output_file = os.path.join(output_dir, f"{base_name}_exported_{timestamp}.csv")
                
                data_to_save = [pc._points]
                header = "X,Y,Z"
                
                for field_name, field_data in pc._scalar_fields.items():
                    data_to_save.append(field_data.reshape(-1, 1))
                    header += f",{field_name}"
                
                combined_data = np.hstack(data_to_save)
                np.savetxt(output_file, combined_data, fmt='%.6f', delimiter=',', header=header, comments='')
                
            elif format_type == "npy":
                # Export as numpy binary with metadata
                output_file = os.path.join(output_dir, f"{base_name}_exported_{timestamp}.npz")
                save_data = {
                    'points': pc._points,
                    'name': pc._name
                }
                for field_name, field_data in pc._scalar_fields.items():
                    save_data[field_name] = field_data
                np.savez_compressed(output_file, **save_data)
                
            else:
                self.showNotification.emit(f"Unsupported export format: {format_type}", "error")
                return None
            
            self.showNotification.emit(f"Exported to: {os.path.basename(output_file)}", "success")
            print(f"Exported results to: {output_file}")
            
            return output_file
            
        except Exception as e:
            self.showNotification.emit(f"Error exporting results: {str(e)}", "error")
            import traceback
            traceback.print_exc()
            return None

    def loadSavedResults(self, file_path):
        """Load previously saved results from NPZ file"""
        try:
            data = np.load(file_path)
            
            # Create StandalonePointCloud from saved data
            class StandalonePointCloud:
                def __init__(self, points, name, file_path):
                    self._points = points
                    self._name = name
                    self._file_path = file_path
                    self._scalar_fields = {}
                    
                def points(self):
                    return self._points
                
                def getName(self):
                    return self._name
                
                def addScalarField(self, name):
                    if name not in self._scalar_fields:
                        self._scalar_fields[name] = np.zeros(len(self._points))
                    return list(self._scalar_fields.keys()).index(name)
                
                def getScalarFieldIndexByName(self, name):
                    if name in self._scalar_fields:
                        return list(self._scalar_fields.keys()).index(name)
                    return -1
                
                def getScalarField(self, index):
                    if isinstance(index, int):
                        name = list(self._scalar_fields.keys())[index]
                    else:
                        name = index
                    
                    class ScalarField:
                        def __init__(self, data):
                            self.data = data
                        def asArray(self):
                            return self.data
                        def computeMinAndMax(self):
                            pass
                    return ScalarField(self._scalar_fields[name])
                
                def setCurrentDisplayedScalarField(self, index):
                    pass
                
                def showSF(self, show):
                    pass
            
            points = data['points']
            name = str(data['name']) if 'name' in data else os.path.basename(file_path)
            
            pc = StandalonePointCloud(points, name, file_path)
            
            # Load all scalar fields
            for key in data.keys():
                if key.startswith('field_'):
                    field_name = key[6:]  # Remove 'field_' prefix
                    pc._scalar_fields[field_name] = data[key]
                elif key not in ['points', 'name']:
                    # Also load fields without prefix (for backward compatibility)
                    pc._scalar_fields[key] = data[key]
            
            self.standalone_point_cloud = [pc]
            self.standalone_file_path = file_path
            
            self.showNotification.emit(f"Loaded results from: {os.path.basename(file_path)}", "success")
            print(f"Loaded {len(pc._scalar_fields)} scalar fields: {list(pc._scalar_fields.keys())}")
            
            return [pc]
            
        except Exception as e:
            self.showNotification.emit(f"Error loading saved results: {str(e)}", "error")
            import traceback
            traceback.print_exc()
            return None

    def checkModelExistence(self,model_path,model_name):
        if not os.path.exists(model_path):
            self.showNotification.emit(f"Model file not found: {model_name}. Please download it first.", "error")
            return False
        return True

    def checkModelExists(self, model_name):
        """Check if the model file exists locally"""
        file_path = os.path.join(self.model_local_path, f"{model_name}.pth")
        return os.path.exists(file_path)

    def checkPointCloudType(self,name):
        if name!= 'ccPointCloud':
            self.showNotification.emit("Please select a point cloud, not other data types", "warning")
            return False



    @pyqtSlot(result=bool)
    def isCudaAvailable(self):
        """Return True if CUDA is available"""
        return self.is_cuda_available

    @pyqtSlot(str, result=bool)
    def openExternalLink(self, url):
        """Open a URL in the system's default browser"""
        try:
            QDesktopServices.openUrl(QUrl(url))
            return True
        except Exception as e:
            self.showNotification.emit(f"Failed to open link: {str(e)}", "error")
            return False
    @pyqtSlot(str, result=bool)
    def downloadModel(self, model_name):
        """Download a model file from the server to local storage in a non-blocking way"""

        # Set up the download in a worker thread
        def download_task():
            try:
                #Due to the GitHub rule, all brackets in released model names were reformatted. 
                url = f"{self.model_server_path}{model_name}.pth".replace("(", "_").replace(")", "")
                local_path = os.path.join(self.model_local_path, f"{model_name}.pth")

                # If file exists, we'll overwrite it
                # In a real application, you might want to add confirmation

                # Create a temporary file first, in case download is interrupted
                temp_path = local_path + ".temp"

                response = requests.get(url, stream=True)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(temp_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
                            downloaded += len(chunk)
                            # Update progress
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                self.progressUpdated.emit(percent)

                # Rename the temp file to the target file once download is complete
                if os.path.exists(local_path):
                    os.remove(local_path)
                os.rename(temp_path, local_path)

                return True

            except requests.exceptions.RequestException as e:
                self.showNotification.emit(f"Failed to download model: {str(e)}", "error")
                return False

        # Create and configure the worker
        worker = Worker(download_task)
        worker.progressUpdated.connect(self.progressUpdated)
        worker.finished.connect(lambda success, result:self._handle_download_result(success, result, model_name))
        worker.errorOccurred.connect(lambda error:self.showNotification.emit(f"Error downloading model: {error}", "error"))

        # Keep a reference to the worker
        self.workers.append(worker)
        worker.start()

        # Return True to indicate download started (not completed)
        return True

    def _handle_download_result(self, success, result, model_name):
        """Handle the results from the worker thread for model download"""
        if success and result:
            self.showNotification.emit(f"Model {model_name} downloaded successfully.", "success")
            # Update the model list to reflect the newly downloaded model
            self.updateModelList.emit(self.getModelList())
        else:
            self.showNotification.emit(f"Failed to download model: {model_name}", "error")

    @pyqtSlot(str)
    def openDirectory(self, dir_type):
        """Open the model or log directory in file explorer"""
        if dir_type == "model":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.model_local_path))
        elif dir_type == "log":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_local_path))

    @pyqtSlot(result=str)
    def getModelList(self):
        """Return the list of available models as JSON string"""
        print("Getting model list from Python backend")

        # Dictionary to track which models are downloaded
        model_status = {}
        for model in self.model_names:
            model_status[model] = self.checkModelExists(model)
            # print(f"Model: {model}, Downloaded: {model_status[model]}")

        result = json.dumps({"models": self.model_names, "status": model_status})
        print(f"Returning model list: {result}")
        return result

    def findLatestProcessedFile(self, base_path, step_prefixes):
        """Find the latest processed LAS file for the given step prefixes"""
        if not base_path:
            return None
        
        base_dir = os.path.dirname(base_path)
        base_name = os.path.splitext(os.path.basename(base_path))[0]
        
        # Remove any existing step suffix from base name
        for suffix in ['_stemcls', '_treeloc', '_treeoff', '_crownoff']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break
        
        # Look for files with step prefixes (in reverse order - most recent first)
        for step_prefix in step_prefixes:
            potential_file = os.path.join(base_dir, f"{base_name}_{step_prefix}.las")
            if os.path.exists(potential_file):
                print(f"Found processed file: {potential_file}")
                return potential_file
        
        # Fall back to original file
        return base_path



    @pyqtSlot(bool, str, bool,str, result=bool)
    def compFilter(self, use_gpu, component_type, if_bottom_only=False,subfolder="filter"):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Apply component filtering called with use_gpu={use_gpu}, component_type={component_type}")
        print(f"Currently selected model: {self.selected_model}")

        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                # Standalone mode - load from file
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False

            model_name = self.selected_model
            print(f"Using model: {model_name}")

            # Configure paths
            config_file = os.path.join(self.current_directory, f'modules/{subfolder}/{model_name}.json')
            model_path = os.path.join(self.model_local_path, f"{model_name}.pth")

            # Check if model exists
            if not self.checkModelExistence(model_path,model_name):
                return False

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd = pc.points()
                # pcd=pcd0[:,:3]-np.min(pcd0[:,:3],0)

                min_res = float(model_name.split("_")[-1].split("cm")[0])#get approx resolution
                nbmat_sz = float(model_name.split("_")[-2])#get approx block size

                block_sz=np.prod(np.floor((np.max(pcd[:,:2],axis=0)-np.min(pcd[:,:2],axis=0))/(min_res*0.01*nbmat_sz)).astype(np.int32))
                if block_sz > 600:
                    response = QMessageBox.question(None, "Confirmation Required", f"The point cloud is quite large — ({int(block_sz)} blocks) at the current voxel resolution — and may take a long time to process. Do you want to continue?",
                                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

                    if response != QMessageBox.StandardButton.Yes:
                        self.showNotification.emit("Operation cancelled by user", "info")
                        return False

                # Get selected model
                if not self.selected_model:
                    self.showNotification.emit("No model selected", "error")
                    return False

                # Import DL filter module
                from modules.filter.componentFilter import filterPoints

                # Set progress to 0%
                self.progressUpdated.emit(5)

                # Create and set up the worker
                worker = Worker(
                    filterPoints,
                    config_file,
                    pcd,
                    model_path,
                    if_bottom_only=if_bottom_only,
                    use_efficient="esegformer" in model_name,
                    use_cuda=use_gpu,
                    progress_callback=self.process_events
                )
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(
                    lambda success, labels: self._handle_compFilter_result(success, labels, pc, component_type))
                worker.errorOccurred.connect(
                    lambda error: self.showNotification.emit(f"Error in {component_type} processing: {error}", "error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                return True

        except Exception as e:
            self.showNotification.emit(f"Error in {component_type} processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_compFilter_result(self, success, labels, pc, component_type):
        """Handle the results from the worker thread for compFilter"""
        if not success or labels is None:
            return

        self.progressUpdated.emit(100)
        try:
            # Update CloudCompare scalar field
            labels_field = pc.getScalarFieldIndexByName(f"{component_type}")
            if labels_field < 0:
                labels_field = pc.addScalarField(f"{component_type}")

            sfArray = pc.getScalarField(labels_field).asArray()
            sfArray[:] = labels
            pc.getScalarField(labels_field).computeMinAndMax()
            pc.setCurrentDisplayedScalarField(labels_field)
            pc.showSF(True)

            # Update UI
            if PYCC_AVAILABLE:
                CC.redrawAll()
                CC.updateUI()

            self.showNotification.emit(f"TreeFilter processing completed for {pc.getName()}", "success")
            
            # Auto-save results in standalone mode
            if not PYCC_AVAILABLE:
                self.saveStandaloneResults(step_name=f"{component_type}")

        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)

    @pyqtSlot(float, int, result=bool)
    def applyNoiseClean(self,max_gap=3.0,min_pts=100):
        if not self.checkSelection():
            return False

        if PYCC_AVAILABLE:
            pcs = CC.getSelectedEntities()
        else:
            pcs = self.loadStandalonePointCloud()
            if pcs is None:
                return False

        try:
            for pc in pcs:
                # pc = CC.getSelectedEntities()[0]
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                pcd0 = pc.points()
                pcd=pcd0[:,:3]-np.min(pcd0[:,:3],0)

                # from pathlib import Path
                current_script_path = os.path.dirname(os.path.realpath(__file__))
                sys.path.append(current_script_path)
                # self.show_info_messagebox(str(self.model_choice_key_words), "warning")
                from modules.treeisonet.cleanSmallerClusters import applySmallClusterClean

                self.progressUpdated.emit(10)

                stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                if stemcls_field >= 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                    stemcls = pc.getScalarField(stemcls_field).asArray()
                    stemind = np.array(stemcls).astype(np.int32) >1
                    pcd_stem = pcd[stemind]
                    conn_labels = applySmallClusterClean(pcd_stem, max_gap, min_pts)
                    removal_ind = conn_labels == 0
                    conn_labels[removal_ind] = 1.0
                    conn_labels[~removal_ind] = 2.0
                    conn_cls = np.ones(len(stemcls))
                    conn_cls[stemind] = conn_labels

                    stemcls[:] = conn_cls
                    pc.getScalarField(stemcls_field).computeMinAndMax()  # must call this before the scalar field is updated in CC
                    pc.setCurrentDisplayedScalarField(stemcls_field)
                    pc.showSF(True)

                else:
                    conn_labels = applySmallClusterClean(pcd, max_gap, min_pts)
                    connected_component_field = pc.getScalarFieldIndexByName("connected_component")
                    if connected_component_field < 0:
                        connected_component_field = pc.addScalarField("connected_component")
                    sfArray = pc.getScalarField(connected_component_field).asArray()
                    sfArray[:] = conn_labels
                    pc.getScalarField(connected_component_field).computeMinAndMax()  # must call this before the scalar field is updated in CC
                    pc.setCurrentDisplayedScalarField(connected_component_field)
                    pc.showSF(True)

                if PYCC_AVAILABLE:
                    CC.redrawAll()
                    CC.updateUI()

            self.progressUpdated.emit(100)
            return True
        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)

    @pyqtSlot(bool, float, float, float, result=bool)
    def createDTM(self, tileEnable, tileSize, bufferSize,resolution):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Creating DTM")
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False
            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field < 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                    self.showNotification.emit("Please extract DTM points by clicking Apply first", "warning")
                    return False

                self.progressUpdated.emit(5)

                treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)

                # self.show_info_messagebox("Selected", "warning")
                pcd = pc.points()
                pcd_new = np.concatenate([pcd[:,:3], treefilter[:, np.newaxis]], axis=1)
                current_script_path = os.path.dirname(os.path.realpath(__file__))
                sys.path.append(current_script_path)

                from modules.filter.createDTM import createDtm
                if tileEnable:
                    tile_size = np.array([tileSize, tileSize])
                    buffer_size = np.array([bufferSize, bufferSize])
                else:
                    tile_size = None
                    buffer_size = None

                dtm = createDtm(pcd_new, resolution=np.array([resolution, resolution]), tile_size=tile_size, buffer_size=buffer_size)
                
                if PYCC_AVAILABLE:
                    dtm_pcd = pycc.ccPointCloud(f"{pc.getName()}_dtm")
                    for dtm_pt in dtm:
                        dtm_pcd.addPoint(cccorelib.CCVector3(dtm_pt[0], dtm_pt[1], dtm_pt[2]))

                    self.progressUpdated.emit(100)

                    pc.addChild(dtm_pcd)
                    CC.addToDB(dtm_pcd)
                    CC.redrawAll()
                    CC.updateUI()
                else:
                    # In standalone mode, save DTM to file
                    self.progressUpdated.emit(100)
                    try:
                        # Use input file directory as output directory
                        if hasattr(pc, '_file_path') and pc._file_path:
                            output_dir = os.path.dirname(pc._file_path)
                        else:
                            output_dir = os.path.join(self.log_local_path, "dtm_results")
                        os.makedirs(output_dir, exist_ok=True)
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        dtm_file = os.path.join(output_dir, f"{pc.getName()}_dtm_{timestamp}.txt")
                        np.savetxt(dtm_file, dtm, fmt='%.6f', header='X Y Z', comments='')
                        print(f"DTM saved to: {dtm_file}")
                        self.showNotification.emit(f"DTM created and saved to {dtm_file}", "success")
                    except Exception as save_error:
                        print(f"Could not save DTM: {save_error}")
                        self.showNotification.emit(f"DTM created ({len(dtm)} points)", "success")
            return True
        except Exception as e:
            self.showNotification.emit(f"Error in DTM creation: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    @pyqtSlot(bool, bool, float,float, float, float, float, float, float, result=bool)
    def treeLoc(self, use_gpu, if_stem, cutoff_thresh, conf_thresh, min_rad, max_gap, nms_thresh,custom_voxel_res_xy,custom_voxel_res_z):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"\n{'='*60}")
        print(f"[TreeLoc] Starting TreeLoc extraction with use_gpu={use_gpu}")
        print(f"[TreeLoc] Currently selected model: {self.selected_model}")
        print(f"[TreeLoc] Parameters: if_stem={if_stem}, cutoff_thresh={cutoff_thresh}, conf_thresh={conf_thresh}")
        print(f"[TreeLoc] Parameters: min_rad={min_rad}, max_gap={max_gap}, nms_thresh={nms_thresh}")
        print(f"[TreeLoc] Custom voxel resolution: XY={custom_voxel_res_xy}, Z={custom_voxel_res_z}")
        print(f"{'='*60}")

        if not self.checkSelection():
            print("[TreeLoc] No point cloud selection found.")
            return False

        try:
            # Get selected entities
            print("[TreeLoc] Retrieving point clouds...")
            if PYCC_AVAILABLE:
                print("[TreeLoc] Using CloudCompare API")
                pcs = CC.getSelectedEntities()
            else:
                # In standalone mode, look for the latest processed file (stemcls)
                # This ensures we load the file with stemcls scalar field
                print("[TreeLoc] Running in standalone mode")
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['stemcls']  # Look for stemcls output first
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"[TreeLoc] Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                print("[TreeLoc] Loading standalone point cloud...")
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    print("[TreeLoc] Failed to load standalone point cloud")
                    return False
            print(f"[TreeLoc] Successfully retrieved point cloud(s)")

            for pc_idx, pc in enumerate(pcs if isinstance(pcs, list) else [pcs]):
                print(f"\n[TreeLoc] Processing point cloud {pc_idx + 1}")
                if self.checkPointCloudType(type(pc).__name__):
                    print("[TreeLoc] Invalid point cloud type")
                    return False

                # Get point cloud data
                print("[TreeLoc] Extracting point cloud data...")
                pcd = pc.points()
                print(f"[TreeLoc] Point cloud contains {len(pcd)} points")

                if len(pcd)<10000:
                    response = QMessageBox.question(None, "Confirmation Required", f"The point cloud has only {len(pcd)}. Make sure you select the correct point cloud(s). Do you want to continue?",
                                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if response != QMessageBox.StandardButton.Yes:
                        self.showNotification.emit("Operation cancelled by user", "info")
                        print("[TreeLoc] Operation cancelled by user due to low point count")
                        return False

                # Get selected model
                if not self.selected_model:
                    self.showNotification.emit("No model selected", "error")
                    print("[TreeLoc] No model selected")
                    return False

                model_name = self.selected_model
                print(f"[TreeLoc] Using model: {model_name}")

                # Configure paths
                config_file = os.path.join(self.current_directory, f'modules/treeisonet/{model_name}.json')
                model_path = os.path.join(self.model_local_path, f"{model_name}.pth")
                print(f"[TreeLoc] Config file: {config_file}")
                print(f"[TreeLoc] Model path: {model_path}")

                # Check if model exists
                if not self.checkModelExistence(model_path, model_name):
                    print(f"[TreeLoc] Model file not found: {model_path}")
                    return False

                # Import DL filter module
                print("[TreeLoc] Importing treeLoc module...")
                from modules.treeisonet.treeLoc import treeLoc
                print("[TreeLoc] treeLoc module imported successfully")

                self.progressUpdated.emit(5)

                # Check for tree filter field
                print("[TreeLoc] Checking for treefilter scalar field...")
                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    print(f"[TreeLoc] Found treefilter field at index {treefilter_field}")
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    pcd_abg = pcd[treefilter_ind]
                    print(f"[TreeLoc] Filtered to {len(pcd_abg)} points using treefilter")
                else:
                    print("[TreeLoc] No treefilter field found, using all points")
                    pcd_abg = pcd
                    treefilter_ind = None

                if if_stem:
                    print("[TreeLoc] if_stem=True, checking for stemcls field...")
                    stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                    if stemcls_field < 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                        self.showNotification.emit("Please extract stems points by running stemcls first", "warning")
                        self.progressUpdated.emit(0)
                        print("[TreeLoc] ERROR: stemcls field not found. Running stemcls is required when if_stem=True")
                        return False
                    print(f"[TreeLoc] Found stemcls field at index {stemcls_field}")
                    stemcls = np.array(pc.getScalarField(stemcls_field).asArray()).astype(np.int32)
                    if treefilter_field >= 0:
                        stemcls=stemcls[treefilter_ind]
                    pcd_abg=pcd_abg[stemcls>1]
                    print(f"[TreeLoc] Filtered to {len(pcd_abg)} stem points")
                else:
                    print("[TreeLoc] if_stem=False, using full point cloud for TreeLoc")

                # Create and configure the worker
                print(f"[TreeLoc] Creating worker thread...")
                print(f"[TreeLoc] Input point cloud shape: {pcd_abg.shape}")
                print(f"[TreeLoc] Config: {config_file}")
                print(f"[TreeLoc] Model: {model_path}")
                print(f"[TreeLoc] GPU: {use_gpu}")
                
                worker = Worker(treeLoc,
                                config_file,
                                pcd_abg,
                                model_path,
                                use_cuda=use_gpu,
                                if_stem=if_stem,
                                cutoff_thresh=cutoff_thresh,
                                custom_resolution=np.array([custom_voxel_res_xy,custom_voxel_res_xy,custom_voxel_res_z]),
                                progress_callback=self.process_events
                                )
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, preds:
                                        self._handle_treeLoc_result(success, preds, pc,if_stem,treefilter_ind,conf_thresh,max_gap,min_rad,nms_thresh))
                worker.errorOccurred.connect(lambda error:
                                             self.showNotification.emit(f"Error in TreeLoc processing: {error}","error"))

                # Keep a reference to the worker
                print(f"[TreeLoc] Starting worker thread...")
                self.workers.append(worker)
                worker.start()
                print(f"[TreeLoc] Worker thread started. Waiting for results...")

                return True

        except Exception as e:
            print(f"[TreeLoc] ERROR: {str(e)}")
            print(f"[TreeLoc] Traceback: {traceback.format_exc()}")
            self.showNotification.emit(f"Error in TreeLoc processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_treeLoc_result(self, success, preds, pc,if_stem,treefilter_ind,conf_thresh,max_gap,min_rad,nms_thresh):
        """Handle the results from the worker thread for treeLoc"""
        if not success or preds is None:
            return

        try:
            # Run the main tree location algorithm
            pcd = pc.points()
            n_pts = len(pcd)
            # Process the results
            if if_stem:
                pred_treeloc_tops=preds
            else:
                pred_treeloc_conf_rads = np.zeros([n_pts, preds.shape[1]], dtype=np.float32)
                if treefilter_ind is not None:
                    pred_treeloc_conf_rads[treefilter_ind, :] = preds
                else:
                    pred_treeloc_conf_rads = preds

                # Post-processing to extract tree locations
                self.progressUpdated.emit(80)
                QApplication.instance().processEvents()

                from modules.treeisonet.treeLoc import postPeakExtraction
                pred_treeloc_tops = postPeakExtraction(
                    pred_treeloc_conf_rads[pred_treeloc_conf_rads[:, -2] > conf_thresh],
                    K=5,
                    max_gap=max_gap,
                    min_rad=min_rad,
                    nms_thresh=nms_thresh
                )
                # pred_treeloc_conf_rads, pred_treeloc_tops = results

                if pred_treeloc_conf_rads is not None:
                    # Update the radius scalar field
                    labels_field = pc.getScalarFieldIndexByName(f"treeloc_radius")
                    if labels_field < 0:
                        labels_field = pc.addScalarField(f"treeloc_radius")

                    sfArray = pc.getScalarField(labels_field).asArray()
                    sfArray[:] = pred_treeloc_conf_rads[:, -1]
                    pc.getScalarField(labels_field).computeMinAndMax()
                    pc.setCurrentDisplayedScalarField(labels_field)

                    # Update the confidence scalar field
                    labels_field = pc.getScalarFieldIndexByName(f"treeloc_conf")
                    if labels_field < 0:
                        labels_field = pc.addScalarField(f"treeloc_conf")

                    sfArray = pc.getScalarField(labels_field).asArray()
                    sfArray[:] = pred_treeloc_conf_rads[:, -2]
                    pc.getScalarField(labels_field).computeMinAndMax()
                    pc.setCurrentDisplayedScalarField(labels_field)
                    pc.showSF(True)

            # Set progress to 100%
            self.progressUpdated.emit(100)
            
            # Create location point cloud (only in CloudCompare mode)
            if PYCC_AVAILABLE:
                loc_pcd = pycc.ccPointCloud(f"{pc.getName()}_loc")
                self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treeloc_tops))}", "success")

                for treeloc_top in pred_treeloc_tops:
                    loc_pcd.addPoint(cccorelib.CCVector3(treeloc_top[0], treeloc_top[1], treeloc_top[2]))

                loc_pcd.setPointSize(16)

                pc.addChild(loc_pcd)
                CC.addToDB(loc_pcd)

                # Update UI
                CC.redrawAll()
                CC.updateUI()
            else:
                # In standalone mode, just show the count
                self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treeloc_tops))}", "success")
                # Optionally save tree locations to a separate file
                try:
                    # Use input file directory as output directory
                    if hasattr(pc, '_file_path') and pc._file_path:
                        output_dir = os.path.dirname(pc._file_path)
                    else:
                        output_dir = os.path.join(self.log_local_path, "tree_locations")
                    os.makedirs(output_dir, exist_ok=True)
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    loc_file = os.path.join(output_dir, f"{pc.getName()}_treeloc_{timestamp}.txt")
                    np.savetxt(loc_file, pred_treeloc_tops, fmt='%.6f', header='X Y Z', comments='')
                    print(f"Tree locations saved to: {loc_file}")
                except Exception as save_error:
                    print(f"Could not save tree locations: {save_error}")

            self.showNotification.emit(f"TreeLoc processing completed for {pc.getName()}", "success")
            
            # Auto-save results in standalone mode
            if not PYCC_AVAILABLE:
                self.saveStandaloneResults(step_name="treeloc")

        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)



    @pyqtSlot(float, float, float, float, result=bool)
    def postRefineTreeLoc(self, conf_thresh, min_rad, max_gap, nms_thresh):
        print(f"Re-run TreeLoc extractions")

        if not self.checkSelection():
            return False

        try:
            pcs = CC.getSelectedEntities()

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd = pc.points()

                conf_field = pc.getScalarFieldIndexByName(f"treeloc_conf")
                if conf_field < 0:
                    self.showNotification.emit("Please apply the TreeLoc first", "warning")
                    return False

                pred_treeloc_conf = np.array(pc.getScalarField(conf_field).asArray()).astype(np.float32)

                rad_field = pc.getScalarFieldIndexByName(f"treeloc_radius")
                if rad_field < 0:
                    self.showNotification.emit("Please apply the TreeLoc first", "warning")
                    return False

                pred_treeloc_rad = np.array(pc.getScalarField(rad_field).asArray()).astype(np.float32)
                pred_treeloc_conf_rads = np.concatenate([pcd[:, :3], pred_treeloc_conf[:, np.newaxis], pred_treeloc_rad[:, np.newaxis]], axis=1)

                from modules.treeisonet.treeLoc import postPeakExtraction

                # Set progress to 5%
                self.progressUpdated.emit(5)

                # Run the peak extraction
                filtered_data = pred_treeloc_conf_rads[pred_treeloc_conf_rads[:, -2] > conf_thresh]
                # QApplication.instance().processEvents()
                self.progressUpdated.emit(10)
                # Create and configure the worker
                worker = Worker(postPeakExtraction,
                                filtered_data,
                                K=5,
                                max_gap=max_gap,
                                min_rad=min_rad,
                                nms_thresh=nms_thresh,
                                progress_callback=self.process_events
                                )
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, pred_treelocs:
                                        self._handle_postRefineTreeLoc_result(success, pred_treelocs, pc))
                worker.errorOccurred.connect(lambda error:
                                             self.showNotification.emit(f"Error in TreeLoc processing: {error}", "error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                return True

        except Exception as e:
            self.showNotification.emit(f"Error in TreeLoc processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_postRefineTreeLoc_result(self, success, pred_treelocs, pc):
        """Handle the results from the worker thread for postRefineTreeLoc"""
        if not success or pred_treelocs is None:
            return

        try:
            # Set progress to 100%
            self.progressUpdated.emit(100)

            # Create location point cloud (only in CloudCompare mode)
            if PYCC_AVAILABLE:
                loc_pcd = pycc.ccPointCloud(f"{pc.getName()}_loc")
                self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treelocs))}", "success")

                for pred_treeloc in pred_treelocs:
                    loc_pcd.addPoint(cccorelib.CCVector3(pred_treeloc[0], pred_treeloc[1], pred_treeloc[2]))

                loc_pcd.setPointSize(16)

                pc.addChild(loc_pcd)
                CC.addToDB(loc_pcd)

                # Update UI
                CC.redrawAll()
                CC.updateUI()
            else:
                # In standalone mode, just show the count
                self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treelocs))}", "success")
                # Save tree locations to a separate file
                try:
                    # Use input file directory as output directory
                    if hasattr(pc, '_file_path') and pc._file_path:
                        output_dir = os.path.dirname(pc._file_path)
                    else:
                        output_dir = os.path.join(self.log_local_path, "tree_locations")
                    os.makedirs(output_dir, exist_ok=True)
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    loc_file = os.path.join(output_dir, f"{pc.getName()}_treeloc_refined_{timestamp}.txt")
                    np.savetxt(loc_file, pred_treelocs, fmt='%.6f', header='X Y Z', comments='')
                    print(f"Refined tree locations saved to: {loc_file}")
                except Exception as save_error:
                    print(f"Could not save tree locations: {save_error}")

            self.showNotification.emit(f"TreeLoc processing completed for {pc.getName()}", "success")

        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)

    @pyqtSlot(bool, float, float, result=bool)
    def treeOff(self, use_gpu, custom_voxel_res_xy, custom_voxel_res_z):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Apply TreeOff segmentation with use_gpu={use_gpu}")
        print(f"Currently selected model: {self.selected_model}")

        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            pcs = CC.getSelectedEntities()
            # Get selected model
            if not self.selected_model:
                self.showNotification.emit("No model selected", "error")
                return False

            model_name = self.selected_model
            print(f"Using model: {model_name}")

            # Configure paths
            config_file = os.path.join(self.current_directory, f'modules/treeisonet/{model_name}.json')
            model_path = os.path.join(self.model_local_path, f"{model_name}.pth")

            # Check if model exists
            if not self.checkModelExistence(model_path,model_name):
                return False

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd = pc.points()

                if pc.getChildrenNumber() == 0:
                    self.showNotification.emit("Please extract tree locations by running TreeLoc first", "warning")
                    return False

                iter = 0
                while (iter < pc.getChildrenNumber()):
                    if type(pc.getChild(iter)).__name__ == 'ccPointCloud':
                        break
                    iter += 1
                if iter == pc.getChildrenNumber():
                    self.showNotification.emit(
                        "Please ensure tree location point cloud placed as a child of the selected point cloud",
                        "warning")
                    self.progressUpdated.emit(0)
                    return False

                treeloc = pc.getChild(iter).points()
                if len(treeloc) == 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                    self.showNotification.emit(
                        "No tree location points. Please extract tree locations by running TreeLoc first", "warning")
                    self.progressUpdated.emit(0)
                    return False

                # Import DL filter module
                from modules.treeisonet.treeOff import treeOff

                # Set progress to 0%
                self.progressUpdated.emit(5)

                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    pcd_abg = pcd[treefilter_ind]
                else:
                    pcd_abg = pcd
                    treefilter_ind = None


                # Create and configure the worker
                worker = Worker(treeOff,
                                config_file,
                                pcd_abg,
                                treeloc,
                                model_path,
                                use_cuda=use_gpu,
                                custom_resolution=np.array([custom_voxel_res_xy,custom_voxel_res_xy,custom_voxel_res_z]),
                                progress_callback=self.process_events
                                )
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, preds:
                                        self._handle_treeOff_result(success, preds, pc, treefilter_ind))
                worker.errorOccurred.connect(lambda error:self.showNotification.emit(f"Error in TreeOff processing: {error}","error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                return True

        except Exception as e:
            self.showNotification.emit(f"Error in TreeOff processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_treeOff_result(self, success, preds, pc, treefilter_ind):
        """Handle the results from the worker thread for treeOff"""
        if not success or preds is None:
            return

        try:
            # Set progress to 100%
            self.progressUpdated.emit(100)

            # Process the results
            pred_treeitc = np.zeros(len(pc.points()), dtype=np.int32)
            if treefilter_ind is not None:
                pred_treeitc[treefilter_ind] = preds
            else:
                pred_treeitc = preds

            # Update CloudCompare scalar field
            labels_field = pc.getScalarFieldIndexByName(f"treeoff")
            if labels_field < 0:
                labels_field = pc.addScalarField(f"treeoff")

            sfArray = pc.getScalarField(labels_field).asArray()
            sfArray[:] = pred_treeitc
            pc.getScalarField(labels_field).computeMinAndMax()
            pc.setCurrentDisplayedScalarField(labels_field)
            pc.showSF(True)

            # Update UI
            if PYCC_AVAILABLE:
                CC.redrawAll()
                CC.updateUI()

            self.showNotification.emit(f"TreeOff processing completed for {pc.getName()}", "success")
            return True

        except Exception as e:
            self.showNotification.emit(f"Error in TreeOff processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    @pyqtSlot(float,float,result=bool)
    def stemClusterSP(self,resolution=0.06,max_gap=0.3):
        print("Apply stemClusterSP")
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                # In standalone mode, load from the latest processed file
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['stemcls']  # Look for stemcls (treeloc doesn't create LAS)
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False
                    
            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False
                # Get point cloud data
                pcd = pc.points()

                self.progressUpdated.emit(5)

                stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                if stemcls_field < 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                    self.showNotification.emit("Please extract stems points by running stemcls first", "warning")
                    self.progressUpdated.emit(0)
                    return False
                stemcls = np.array(pc.getScalarField(stemcls_field).asArray()).astype(np.int32)

                # Get tree locations (stem base points)
                stembase = None
                if PYCC_AVAILABLE:
                    # CloudCompare mode - get from child point cloud
                    if pc.getChildrenNumber() == 0:
                        self.showNotification.emit("Please extract stems locations by running treeloc first", "warning")
                        self.progressUpdated.emit(0)
                        return False
                    iter = 0
                    while (iter < pc.getChildrenNumber()):
                        # self.show_info_messagebox((type(pc.getChild(iter)).__name__), "warning")
                        if type(pc.getChild(iter)).__name__ == 'ccPointCloud':
                            break
                        iter += 1
                    if iter == pc.getChildrenNumber():
                        self.showNotification.emit("Please ensure stem_base point cloud placed as a child of the selected point cloud", "warning")
                        self.progressUpdated.emit(0)
                        return False

                    stembase = pc.getChild(iter).points()
                    if len(stembase) == 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                        self.showNotification.emit("No stem points. Please extract stems locations by running treeloc first", "warning")
                        self.progressUpdated.emit(0)
                        return False
                else:
                    # Standalone mode - load tree locations from saved text file
                    if hasattr(pc, '_file_path') and pc._file_path:
                        base_dir = os.path.dirname(pc._file_path)
                        base_name = os.path.splitext(os.path.basename(pc._file_path))[0]
                        base_name_original = base_name  # Keep original name with suffix
                        # Remove step suffix to get original name
                        for suffix in ['_stemcls', '_treeloc', '_treeoff', '_crownoff']:
                            if base_name.endswith(suffix):
                                base_name = base_name[:-len(suffix)]
                                break
                        
                        # Look for the most recent tree location file
                        import glob
                        print(f"Debug: Looking for tree locations in: {base_dir}")
                        print(f"Debug: Base name: {base_name}")
                        print(f"Debug: Original name: {base_name_original}")
                        
                        # Try multiple patterns to find tree location files
                        patterns_to_try = [
                            os.path.join(base_dir, f"{base_name_original}.las_treeloc_*.txt"),  # With step suffix + .las
                            os.path.join(base_dir, f"{base_name}.las_treeloc_*.txt"),           # Without step suffix + .las
                            os.path.join(base_dir, f"{base_name_original}_treeloc_*.txt"),      # With step suffix, no .las
                            os.path.join(base_dir, f"{base_name}_treeloc_*.txt")                # Without step suffix, no .las
                        ]
                        
                        loc_files = []
                        for i, pattern in enumerate(patterns_to_try):
                            print(f"Debug: Search pattern {i+1}: {pattern}")
                            found = glob.glob(pattern)
                            if found:
                                loc_files.extend(found)
                                print(f"Debug: Found {len(found)} files with pattern {i+1}")
                        
                        # Remove duplicates while preserving order
                        loc_files = list(dict.fromkeys(loc_files))
                        
                        print(f"Debug: Total found {len(loc_files)} tree location files")
                        if loc_files:
                            print(f"Debug: Files found: {loc_files}")
                        
                        if loc_files:
                            # Get the most recent file
                            latest_loc_file = max(loc_files, key=os.path.getmtime)
                            print(f"Loading tree locations from: {latest_loc_file}")
                            try:
                                # Skip header line when loading
                                stembase = np.loadtxt(latest_loc_file, skiprows=1)
                                if stembase.ndim == 1:
                                    stembase = stembase.reshape(1, -1)
                                print(f"Loaded {len(stembase)} tree locations")
                            except Exception as e:
                                print(f"Error loading tree locations: {e}")
                                # Try without skiprows in case there's no header
                                try:
                                    stembase = np.loadtxt(latest_loc_file)
                                    if stembase.ndim == 1:
                                        stembase = stembase.reshape(1, -1)
                                except:
                                    self.showNotification.emit(f"Error reading tree location file: {str(e)}", "error")
                                    self.progressUpdated.emit(0)
                                    return False
                        else:
                            self.showNotification.emit("Please extract tree locations by running treeloc first", "warning")
                            self.progressUpdated.emit(0)
                            return False
                    else:
                        self.showNotification.emit("Cannot find tree location file", "warning")
                        self.progressUpdated.emit(0)
                        return False
                    
                    if len(stembase) == 0:
                        self.showNotification.emit("No tree locations found. Please run treeloc first", "warning")
                        self.progressUpdated.emit(0)
                        return False

                from modules.treeisonet.stemCluster import shortestpath3D

                # Create and configure the worker
                worker = Worker(shortestpath3D,
                                pcd,
                                stemcls,
                                stembase,
                                min_res=resolution,
                                max_isolated_distance=max_gap,
                                progress_callback=self.process_events
                                )

                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, preds:self._handle_stemClusterSP_result(success, preds, pc))
                worker.errorOccurred.connect(lambda error:self.showNotification.emit(f"Error in clustering stem points: {str(error)}", "error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                return True
        except Exception as e:
            self.showNotification.emit(f"Error in clustering stem points: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_stemClusterSP_result(self, success, stemoff, pc):
        """Handle the results from the worker thread for stemClusterSP"""
        if not success or stemoff is None:
            return

        try:
            # Set progress to 100%
            self.progressUpdated.emit(100)
            stemoff_field = pc.getScalarFieldIndexByName("stemoff")
            if stemoff_field < 0:
                stemoff_field = pc.addScalarField("stemoff")
            sfArray = pc.getScalarField(stemoff_field).asArray()
            sfArray[:] = stemoff
            pc.getScalarField(stemoff_field).computeMinAndMax()  # must call this before the scalar field is updated in CC
            pc.setCurrentDisplayedScalarField(stemoff_field)
            pc.showSF(True)

            if PYCC_AVAILABLE:
                CC.redrawAll()
                CC.updateUI()
            else:
                # Auto-save in standalone mode
                self.saveStandaloneResults(step_name="stemoff")

            self.showNotification.emit(f"stemClusterSP processing completed for {pc.getName()}", "success")

            return True
        except Exception as e:
            self.showNotification.emit(f"Error in stemClusterSP processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    @pyqtSlot(float,int,float,float,result=bool)
    def crownClusterSP(self,resolution=0.06,K=5,reg_strength=1.0,max_gap=0.3):
        print("Apply crownClusterSP")
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                # In standalone mode, load from the latest processed file
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['stemoff', 'stemcls']  # Look for stemoff or stemcls
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd0 = pc.points()
                pcd=pcd0[:,:3]-np.min(pcd0[:,:3],0)
                # n_pts=len(pcd)

                stemoff_field = pc.getScalarFieldIndexByName("stemoff")
                if stemoff_field < 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                    self.showNotification.emit("Please isolate stems points by running stemClusterSP first", "warning")
                    return False
                stemoff = np.array(pc.getScalarField(stemoff_field).asArray()).astype(np.int32)

                self.progressUpdated.emit(5)

                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    pcd_abg = pcd[treefilter_ind,:3]
                    stemoff_abg = stemoff[treefilter_ind]
                else:
                    pcd_abg = pcd[:,:3]
                    stemoff_abg = stemoff
                    treefilter_ind = None

                from modules.treeisonet.crownCluster import init_cutpursuit

                    # print("Starting init_segs")
                    # init_segs, n_segs = init_cutpursuit(pcd_abg, K=K, reg_strength=reg_strength, resolution=resolution,progress_callback=wrapped_callback)
                    # print("Finished init_segs")
                    # pred_itc = shortestpath3D(pcd_abg, stemoff_abg, init_segs, min_res=resolution,max_isolated_distance=max_gap,progress_callback=wrapped_callback)
                    # print("Finished clustering")
                    # itc = np.zeros(n_pts, dtype=np.int32)
                    # if treefilter_ind is not None:
                    #     itc[treefilter_ind] = pred_itc
                    # else:
                    #     itc = pred_itc
                    # return itc

                # Create and configure the worker
                worker = Worker(init_cutpursuit,pcd_abg, min_res=resolution, K=K, reg_strength=reg_strength, progress_callback=self.process_events)
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, results:self._handle_crownClusterSP_result(success, results, pc,pcd_abg,treefilter_ind, stemoff_abg,resolution,max_gap))
                worker.errorOccurred.connect(lambda error:self.showNotification.emit(f"Error in clustering crowns to stems: {str(error)}", "error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()
                return True

        except Exception as e:
            self.showNotification.emit(f"Error in clustering crowns to stems: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False


    def _handle_crownClusterSP_result(self, success, results, pc, pcd_abg,treefilter_ind, stemoff_abg,resolution,max_gap):
        """Handle the results from the worker thread for crownClusterSP"""
        if not success or results is None:
            return

        try:
            init_segs, n_segs = results

            from modules.treeisonet.crownCluster import shortestpath3D
            pred_itc = shortestpath3D(pcd_abg, stemoff_abg, init_segs, min_res=resolution,max_isolated_distance=max_gap)
            print("Finished clustering")
            itc = np.zeros(len(pc.points()), dtype=np.int32)
            if treefilter_ind is not None:
                itc[treefilter_ind] = pred_itc
            else:
                itc = pred_itc

            # Set progress to 100%
            self.progressUpdated.emit(100)
            itc_field = pc.getScalarFieldIndexByName("itc")
            if itc_field < 0:
                itc_field = pc.addScalarField("itc")
            sfArray = pc.getScalarField(itc_field).asArray()

            sfArray[:] = itc
            pc.getScalarField(itc_field).computeMinAndMax()  # must call this before the scalar field is updated in CC
            pc.setCurrentDisplayedScalarField(itc_field)
            pc.showSF(True)

            if PYCC_AVAILABLE:
                CC.redrawAll()
                CC.updateUI()
            else:
                # Auto-save in standalone mode
                self.saveStandaloneResults(step_name="itc")

            self.showNotification.emit(f"crownClusterSP processing completed for {pc.getName()}", "success")

            return True
        except Exception as e:
            self.showNotification.emit(f"Error in crownClusterSP processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False


    @pyqtSlot(bool, result=bool)
    def crownOff(self, use_gpu):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Apply crownoff with use_gpu={use_gpu}")
        print(f"Currently selected model: {self.selected_model}")

        if not self.checkSelection():
            return False

        try:
            print("[CrownOff] Starting crownOff processing pipeline...")
            
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
                print(f"[CrownOff] CloudCompare mode - Found {len(pcs)} point cloud(s)")
            else:
                # In standalone mode, load from the latest processed file
                print("[CrownOff] Standalone mode - Loading point cloud from file...")
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['stemoff', 'stemcls']  # Look for stemoff first, then stemcls
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"[CrownOff] Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    print("[CrownOff] ERROR: Failed to load standalone point cloud")
                    return False
                print(f"[CrownOff] Successfully loaded {len(pcs) if pcs else 0} point cloud(s)")

            model_name = self.selected_model
            print(f"[CrownOff] Using model: {model_name}")

            # Configure paths
            config_file = os.path.join(self.current_directory, f'modules/treeisonet/{model_name}.json')
            model_path = os.path.join(self.model_local_path, f"{model_name}.pth")
            print(f"[CrownOff] Config file: {config_file}")
            print(f"[CrownOff] Model path: {model_path}")

            # Check if model exists
            if not self.checkModelExistence(model_path, model_name):
                print(f"[CrownOff] ERROR: Model file not found or not available")
                return False
            print(f"[CrownOff] Model verified - Ready to process")

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                print(f"[CrownOff] Processing point cloud: {pc.getName() if hasattr(pc, 'getName') else 'Unknown'}")
                
                # Get point cloud data
                pcd = pc.points()
                print(f"[CrownOff] Total points in cloud: {len(pcd):,}")
                
                # Get selected model
                if not self.selected_model:
                    print("[CrownOff] ERROR: No model selected")
                    self.showNotification.emit("No model selected", "error")
                    return False

                # Import DL filter module
                print("[CrownOff] Importing crownOff module...")
                from modules.treeisonet.crownOff import crownOff
                
                # Set progress to 0%
                self.progressUpdated.emit(5)
                print("[CrownOff] Progress: 5%")

                print("[CrownOff] Checking for stemoff scalar field...")
                itc_field = pc.getScalarFieldIndexByName(f"stemoff")
                if itc_field < 0:
                    print("[CrownOff] ERROR: stemoff field not found")
                    self.showNotification.emit("Please apply the StemClustering SP first", "warning")
                    self.progressUpdated.emit(0)
                    return
                stem_id = np.array(pc.getScalarField(itc_field).asArray()).astype(np.int32)
                print(f"[CrownOff] Loaded stemoff field with {len(stem_id):,} values")

                print("[CrownOff] Checking for treefilter scalar field...")
                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    filtered_count = np.sum(treefilter_ind)
                    print(f"[CrownOff] Treefilter found - Using {filtered_count:,} filtered points out of {len(pcd):,}")
                    pcd_abg = pcd[treefilter_ind]
                    stem_id = stem_id[treefilter_ind]
                else:
                    print("[CrownOff] Treefilter not found - Using all points")
                    pcd_abg = pcd
                    treefilter_ind = None

                print(f"[CrownOff] Points to process: {len(pcd_abg):,}")
                print("[CrownOff] Creating worker thread for crownOff inference...")
                
                # Create and set up the worker
                worker = Worker(crownOff,
                                config_file,
                                pcd_abg,
                                stem_id,
                                model_path,
                                use_cuda=use_gpu,
                                progress_callback=self.process_events
                                )
                worker.progressUpdated.connect(self.progressUpdated)
                worker.finished.connect(lambda success, preds: self._handle_crownoff_result(success, preds, pc, treefilter_ind))
                worker.errorOccurred.connect(lambda error: self.showNotification.emit(f"Error in crownoff processing: {error}", "error"))

                print("[CrownOff] Starting worker thread...")
                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                print("[CrownOff] Worker thread started - Processing in background...")
                return True

        except Exception as e:
            print(f"[CrownOff] ERROR: Exception occurred: {str(e)}")
            import traceback
            traceback.print_exc()
            self.showNotification.emit(f"Error in crownoff processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_crownoff_result(self, success, preds, pc,treefilter_ind):
        """Handle the results from the worker thread for crownOff"""
        print("[CrownOff] Result handler called - Processing predictions...")
        print(f"[CrownOff] Success: {success}, Predictions shape: {preds.shape if preds is not None else 'None'}")
        
        if not success or preds is None:
            print("[CrownOff] ERROR: Worker thread failed or returned None predictions")
            self.showNotification.emit("Error in crownoff neural network processing", "error")
            self.progressUpdated.emit(0)
            return
        
        print(f"[CrownOff] Processing {len(preds):,} predictions from neural network...")
        self.progressUpdated.emit(70)
        
        try:
            # Process the results
            print(f"[CrownOff] Creating predictions array for point cloud with {len(pc.points()):,} points...")
            pred_treeitc = np.zeros(len(pc.points()), dtype=np.int32)
            
            if treefilter_ind is not None:
                print(f"[CrownOff] Mapping predictions back to original point cloud (using treefilter mask)...")
                pred_treeitc[treefilter_ind] = preds
                crown_count = np.sum(preds > 0)
                print(f"[CrownOff] Predictions mapped - Crown points: {crown_count:,}, Non-crown: {len(preds) - crown_count:,}")
            else:
                print(f"[CrownOff] Using predictions directly (no filtering applied)...")
                pred_treeitc = preds
                crown_count = np.sum(preds > 0)
                print(f"[CrownOff] Crown points: {crown_count:,}, Non-crown: {len(preds) - crown_count:,}")
            
            if PYCC_AVAILABLE:
                # CloudCompare mode
                print(f"[CrownOff] CloudCompare mode - Adding scalar field...")
                labels_field = pc.getScalarFieldIndexByName("itc")
                if labels_field < 0:
                    labels_field = pc.addScalarField("itc")
                    print(f"[CrownOff] Created new 'itc' scalar field")
                else:
                    print(f"[CrownOff] Updated existing 'itc' scalar field")

                print(f"[CrownOff] Populating scalar field with {len(pred_treeitc):,} values...")
                sfArray = pc.getScalarField(labels_field).asArray()
                sfArray[:] = pred_treeitc
                pc.getScalarField(labels_field).computeMinAndMax()
                
                # Get min/max from the array directly
                min_val = np.min(pred_treeitc)
                max_val = np.max(pred_treeitc)
                print(f"[CrownOff] Scalar field statistics - Min: {min_val}, Max: {max_val}")
                
                pc.setCurrentDisplayedScalarField(labels_field)
                pc.showSF(True)
                print(f"[CrownOff] Display updated to show 'itc' scalar field")
                
                print(f"[CrownOff] CloudCompare mode - Redrawing and updating UI...")
                CC.redrawAll()
                CC.updateUI()
            else:
                # Standalone mode - update LAS file
                print(f"[CrownOff] Standalone mode - Updating point cloud with predictions...")
                print(f"[CrownOff] Adding 'itc' field to point cloud...")
                
                # Store predictions in the point cloud's scalar fields dictionary
                # This ensures the field will be saved to the output LAS file
                if len(self.standalone_point_cloud) > 0:
                    pc = self.standalone_point_cloud[0]
                    pc._scalar_fields['itc'] = pred_treeitc.astype(np.float32)
                    print(f"[CrownOff] Stored 'itc' field in point cloud scalar fields")
                    
                    # Get min/max
                    min_val = np.min(pred_treeitc)
                    max_val = np.max(pred_treeitc)
                    print(f"[CrownOff] Predictions statistics - Min: {min_val}, Max: {max_val}")
                
                print(f"[CrownOff] Standalone mode - Auto-saving results...")
                self.saveStandaloneResults(step_name="crownoff")
                print(f"[CrownOff] Results saved successfully")

            print(f"[CrownOff] Processing complete!")
            self.showNotification.emit(f"CrownOff processing completed", "success")
            self.progressUpdated.emit(100)

        except Exception as e:
            print(f"[CrownOff] ERROR during result handling: {str(e)}")
            import traceback
            traceback.print_exc()
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)
            self.progressUpdated.emit(0)


    @pyqtSlot(float,result=bool)
    def treeStat(self,dtm_resolution):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print("Apply TreeStat")
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            pcs = CC.getSelectedEntities()

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd = pc.points()


                from modules.treeisonet.treeStat import treeStat

                # Set progress to 0%
                self.progressUpdated.emit(5)

                itc_field = pc.getScalarFieldIndexByName(f"treeoff")
                if itc_field < 0:
                    itc_field = pc.getScalarFieldIndexByName(f"itc")
                if itc_field < 0:
                    self.showNotification.emit("Please apply the TreeOff first", "warning")
                    self.progressUpdated.emit(0)
                    return
                itc_id = np.array(pc.getScalarField(itc_field).asArray()).astype(np.int32)

                treefilter_field = pc.getScalarFieldIndexByName(f"treefilter")
                if treefilter_field>=0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                else:
                    treefilter=None

                outpath = os.path.join(self.log_local_path, f"{pc.getName()}_treestat.csv")
                global_shift=pc.getGlobalShift()
                # print(global_shift)
                pcd_min=np.array([-global_shift.x,-global_shift.y,-global_shift.z])
                treeStat(pcd,itc_id,pcd_min=pcd_min,treefilter=treefilter,outpath=outpath,dtm_resolution=dtm_resolution,progress_callback=lambda p: self.progressUpdated.emit(p))
                self.showNotification.emit(f"TreeStat completed {pc.getName()}. Please open the output folder.", "success")
                self.progressUpdated.emit(100)
                return True
        except Exception as e:
            self.showNotification.emit(f"Error in extracting tree stats: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False



    @pyqtSlot(int, float, int, float, result=bool)
    def applyQSMInitSegmentation(self, stem_k, stem_strength, branch_k, branch_strength):
        """Apply initial segmentation for QSM"""
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                # In standalone mode, load from the latest processed file
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['crownoff', 'stemoff', 'stemcls']  # Look for latest processing step
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd0 = pc.points()
                pcd=pcd0[:,:3]-np.min(pcd0[:,:3],0)
                n_pts = len(pcd)

                # Check for stemcls field
                stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                if stemcls_field < 0:
                    self.showNotification.emit("Please extract stem points by running stemcls first", "warning")
                    return False

                stemcls = np.array(pc.getScalarField(stemcls_field).asArray()).astype(np.float32)

                # Combine point coordinates with stem classification
                pcd_with_class = np.concatenate([pcd.astype(np.float32), stemcls[:, np.newaxis]], axis=1)

                # Check for branch classification
                branchcls_field = pc.getScalarFieldIndexByName("branchcls")
                if branchcls_field >= 0:
                    branchcls = np.array(pc.getScalarField(branchcls_field).asArray()).astype(np.float32)
                    branch_ind = branchcls > 1.0
                    pcd_with_class = pcd_with_class[branch_ind]

                # Import QSM module
                from modules.qsm import applyQSM

                # Set progress to 0%
                self.progressUpdated.emit(5)

                # Apply initial segmentation
                init_segs_labels = applyQSM.initSegmentation(
                    pcd_with_class,
                    stem_k,
                    stem_strength,
                    branch_k,
                    branch_strength,
                    progress_callback=lambda p: self.progressUpdated.emit(p)
                )

                # Prepare results for all points
                init_segs = np.zeros(n_pts, dtype=np.int32)
                if branchcls_field >= 0:
                    init_segs[branch_ind] = init_segs_labels
                else:
                    init_segs = init_segs_labels

                # Update CloudCompare scalar field
                init_segs_field = pc.getScalarFieldIndexByName("init_segs")
                if init_segs_field < 0:
                    init_segs_field = pc.addScalarField("init_segs")

                sfArray = pc.getScalarField(init_segs_field).asArray()
                sfArray[:] = init_segs
                pc.getScalarField(init_segs_field).computeMinAndMax()
                pc.setCurrentDisplayedScalarField(init_segs_field)
                pc.showSF(True)

                # Update UI
                if PYCC_AVAILABLE:
                    CC.redrawAll()
                    CC.updateUI()
                else:
                    # Auto-save in standalone mode
                    self.saveStandaloneResults(step_name="init_segs")

                self.progressUpdated.emit(100)
                self.showNotification.emit(f"Initial segmentation completed for {pc.getName()}", "success")

            return True

        except Exception as e:
            self.showNotification.emit(f"Error in initial segmentation: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False



    @pyqtSlot(float, float, result=bool)
    def applyQSM(self, gap_connectivity, max_gap):
        """Apply QSM to create tree structure models"""
        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            if PYCC_AVAILABLE:
                pcs = CC.getSelectedEntities()
            else:
                # In standalone mode, load from the latest processed file
                if hasattr(self, 'standalone_file_path') and self.standalone_file_path:
                    latest_file = self.findLatestProcessedFile(
                        self.standalone_file_path, 
                        ['init_segs', 'crownoff', 'stemoff', 'stemcls']  # Look for init_segs first
                    )
                    if latest_file != self.standalone_file_path:
                        print(f"Loading from processed file: {latest_file}")
                        self.standalone_file_path = latest_file
                
                pcs = self.loadStandalonePointCloud()
                if pcs is None:
                    return False

            for pc in pcs:
                if self.checkPointCloudType(type(pc).__name__):
                    return False

                # Get point cloud data
                pcd = pc.points()
                n_pts = len(pcd)

                # Check for stemcls field
                stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                if stemcls_field < 0:
                    self.showNotification.emit("Please extract stem points by running stemcls first", "warning")
                    return False

                # Check for initial segmentation
                init_segs_field = pc.getScalarFieldIndexByName("init_segs")
                if init_segs_field < 0:
                    self.showNotification.emit("Please run initial segmentation first", "warning")
                    return False

                stemcls = np.array(pc.getScalarField(stemcls_field).asArray()).astype(np.float32)
                init_segs = np.array(pc.getScalarField(init_segs_field).asArray()).astype(np.float32)

                # Normalize stem class values
                stemcls = stemcls - np.min(stemcls)

                # Combine point coordinates with stem classification and initial segmentation
                pcd_with_class = np.concatenate([
                    pcd.astype(np.float32),
                    stemcls[:, np.newaxis],
                    init_segs[:, np.newaxis]
                ], axis=1)

                # Check for branch classification
                branchcls_field = pc.getScalarFieldIndexByName("branchcls")
                if branchcls_field >= 0:
                    branchcls = np.array(pc.getScalarField(branchcls_field).asArray()).astype(np.float32)
                    branch_ind = branchcls > 1.0
                    pcd_with_class = pcd_with_class[branch_ind]

                # Import QSM module
                from modules.qsm import applyQSM

                # Set progress to 0%
                self.progressUpdated.emit(5)

                print(f"[QSM] Starting QSM processing...")
                print(f"[QSM] Input point cloud shape: {pcd_with_class.shape}")
                print(f"[QSM] Gap connectivity: {gap_connectivity}, Max gap: {max_gap}")

                # Apply QSM
                try:
                    print(f"[QSM] Calling applyQSM.applyQSM()...")
                    tree, segs_centroids, segs_labels, tree_centroid_radius = applyQSM.applyQSM(
                        pcd_with_class,
                        max_connectivity_search_distance=gap_connectivity,
                        occlusion_distance_cutoff=max_gap,
                        progress_callback=lambda p: self.progressUpdated.emit(p)
                    )
                    print(f"[QSM] QSM completed successfully")
                    print(f"[QSM] Tree structure type: {type(tree)}, length: {len(tree)}")
                    print(f"[QSM] Segment centroids type: {type(segs_centroids)}, shape/length: {segs_centroids.shape if hasattr(segs_centroids, 'shape') else len(segs_centroids)}")
                    print(f"[QSM] Segment labels type: {type(segs_labels)}, shape/length: {segs_labels.shape if hasattr(segs_labels, 'shape') else len(segs_labels)}")
                    print(f"[QSM] Tree centroid radius type: {type(tree_centroid_radius)}, shape/length: {tree_centroid_radius.shape if hasattr(tree_centroid_radius, 'shape') else len(tree_centroid_radius)}")
                    
                    # Debug: Check segs_centroids dimensions
                    if hasattr(segs_centroids, 'shape'):
                        print(f"[QSM] segs_centroids.shape: {segs_centroids.shape}")
                        if len(segs_centroids.shape) == 1:
                            print(f"[QSM WARNING] segs_centroids is 1D array! Expected 2D array with shape (n_segments, 3)")
                            print(f"[QSM] First 10 elements of segs_centroids: {segs_centroids[:10]}")
                        else:
                            print(f"[QSM] First 3 centroids: {segs_centroids[:3]}")
                    
                    # Debug: print first few branches
                    for i, branch in enumerate(tree[:min(3, len(tree))]):  # First 3 branches
                        print(f"[QSM] Branch {i}: type={type(branch)}, length={len(branch) if hasattr(branch, '__len__') else 'N/A'}")
                        if hasattr(branch, '__iter__'):
                            branch_list = list(branch)[:5]
                            print(f"[QSM]   First nodes: {branch_list}")
                            print(f"[QSM]   Node types: {[type(n) for n in branch_list]}")
                        
                except Exception as qsm_error:
                    print(f"[QSM ERROR] Error during applyQSM call: {qsm_error}")
                    print(f"[QSM ERROR] Error type: {type(qsm_error).__name__}")
                    import traceback
                    print(f"[QSM ERROR] Full traceback:")
                    traceback.print_exc()
                    raise

                # Create branch medial structure (only in CloudCompare mode)
                if PYCC_AVAILABLE:
                    print(f"[QSM] Creating branch medial structure in CloudCompare...")
                    pcd_wrapper = pycc.ccHObject(f"{pc.getName()}_branch_medial")

                    for i, branch in enumerate(tree):
                        print(f"[QSM] Processing branch {i}/{len(tree)}: type={type(branch)}, length={len(branch) if hasattr(branch, '__len__') else 'N/A'}")
                        branch_medial_pcd = pycc.ccPointCloud(f"{pc.getName()}_branch_medial")

                        for node_idx, node in enumerate(branch):
                            try:
                                print(f"[QSM DEBUG] Branch {i}, Node {node_idx}: node={node}, type={type(node)}")
                                
                                # Check if segs_centroids is 1D or 2D
                                if hasattr(segs_centroids, 'ndim'):
                                    if segs_centroids.ndim == 1:
                                        print(f"[QSM ERROR] segs_centroids is 1D! Cannot index with [node][0]")
                                        print(f"[QSM ERROR] segs_centroids shape: {segs_centroids.shape}")
                                        print(f"[QSM ERROR] Attempting to access node index: {node}")
                                        raise IndexError(f"segs_centroids is 1D (shape {segs_centroids.shape}), but trying to access 2D index [node][0]")
                                
                                if node >= len(segs_centroids):
                                    print(f"[QSM ERROR] Branch {i}, Node {node_idx}: node index {node} >= segs_centroids length {len(segs_centroids)}")
                                    print(f"[QSM ERROR] Branch content: {branch}")
                                    raise IndexError(f"Node index {node} out of range for segs_centroids (length {len(segs_centroids)})")
                                
                                print(f"[QSM DEBUG] Accessing segs_centroids[{node}]...")
                                centroid = segs_centroids[node]
                                print(f"[QSM DEBUG] Centroid type: {type(centroid)}, value: {centroid}")
                                
                                # Check centroid dimensions
                                if hasattr(centroid, '__len__'):
                                    print(f"[QSM DEBUG] Centroid length: {len(centroid)}")
                                    if len(centroid) >= 3:
                                        branch_medial_pcd.addPoint(cccorelib.CCVector3(
                                            centroid[0],
                                            centroid[1],
                                            centroid[2]
                                        ))
                                    else:
                                        print(f"[QSM ERROR] Centroid has insufficient dimensions: {len(centroid)}")
                                        raise ValueError(f"Centroid at index {node} has only {len(centroid)} dimensions, expected 3")
                                else:
                                    print(f"[QSM ERROR] Centroid is not array-like: {centroid}")
                                    raise ValueError(f"Centroid at index {node} is not array-like: {type(centroid)}")
                                    
                            except Exception as node_error:
                                print(f"[QSM ERROR] Failed to add node {node_idx} (index {node}): {node_error}")
                                print(f"[QSM ERROR] Error type: {type(node_error).__name__}")
                                import traceback
                                print(f"[QSM ERROR] Traceback:")
                                traceback.print_exc()
                                raise

                        branch_polyline = pycc.ccPolyline(branch_medial_pcd)
                        branch_polyline.setClosed(False)
                        branch_polyline.addPointIndex(0, branch_medial_pcd.size())

                        if i == 0:
                            branch_polyline.setName(f"Stem")
                        else:
                            branch_polyline.setName(f"Branch_{i}")

                        pcd_wrapper.addChild(branch_polyline)
                        CC.addToDB(branch_polyline)

                    CC.addToDB(pcd_wrapper)
                    print(f"[QSM] Branch medial structure created successfully")

                # Save tree structure to OBJ and XML files
                print(f"[QSM] Saving tree structure to OBJ and XML...")
                obj_path = os.path.join(self.log_local_path, f"{pc.getName()}_woodobj.obj")
                xml_path = os.path.join(self.log_local_path, f"{pc.getName()}_wood.xml")

                try:
                    applyQSM.saveTreeToObj(tree_centroid_radius, obj_path)
                    print(f"[QSM] OBJ file saved: {obj_path}")
                except Exception as obj_error:
                    print(f"[QSM ERROR] Failed to save OBJ: {obj_error}")
                    import traceback
                    traceback.print_exc()
                    raise
                
                try:
                    applyQSM.saveTreeToXML(tree, tree_centroid_radius, xml_path)
                    print(f"[QSM] XML file saved: {xml_path}")
                except Exception as xml_error:
                    print(f"[QSM ERROR] Failed to save XML: {xml_error}")
                    import traceback
                    traceback.print_exc()
                    raise

                self.progressUpdated.emit(90)

                # Load the OBJ file into CloudCompare
                if PYCC_AVAILABLE:
                    params = pycc.FileIOFilter.LoadParameters()
                    params.parentWidget = CC.getMainWindow()
                    obj = CC.loadFile(obj_path, params)

                # Update segmentation scalar field
                segs_field = pc.getScalarFieldIndexByName("segs")
                if segs_field < 0:
                    segs_field = pc.addScalarField("segs")

                sfArray = pc.getScalarField(segs_field).asArray()

                if branchcls_field >= 0:
                    sfArray[:] = np.zeros(n_pts)
                    sfArray[branch_ind] = segs_labels
                else:
                    sfArray[:] = segs_labels

                pc.getScalarField(segs_field).computeMinAndMax()
                pc.setCurrentDisplayedScalarField(segs_field)
                pc.showSF(True)

                # Update UI
                if PYCC_AVAILABLE:
                    CC.redrawAll()
                    CC.updateUI()
                else:
                    # Auto-save in standalone mode
                    self.saveStandaloneResults(step_name="qsm")
                    # Note: OBJ and XML files are already saved separately

                self.progressUpdated.emit(100)
                self.showNotification.emit(f"QSM processing completed for {pc.getName()}", "success")

            return True

        except Exception as e:
            self.showNotification.emit(f"Error in QSM processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    @pyqtSlot(str, result=bool)
    def copyToClipboard(self, text):
        """Copy text to clipboard"""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.showNotification.emit("Text copied to clipboard", "success")
            return True
        except Exception as e:
            self.showNotification.emit(f"Failed to copy text: {str(e)}", "error")
            return False

    @pyqtSlot(str, result=str)
    def getSelectedModel(self, model_name):
        """Store and return the currently selected model from the UI"""
        print(f"Python received selected model: {model_name}")
        # Store the selected model name for use in other methods
        self.selected_model = model_name
        return model_name

    @pyqtSlot(result=str)
    def selectPointCloudFile(self):
        """Open file dialog to select point cloud file for standalone mode"""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Point Cloud File",
            "",
            "Point Cloud Files (*.ply *.pcd *.las *.laz *.txt *.xyz *.pts);;All Files (*)"
        )
        if file_path:
            self.standalone_file_path = file_path
            # Clear cached point cloud when new file is selected
            self.standalone_point_cloud = None
            self.showNotification.emit(f"Selected file: {os.path.basename(file_path)}", "success")
            return file_path
        return ""

    @pyqtSlot(str, result=str)
    def exportResults(self, format_type="txt"):
        """Export processing results to file - callable from UI"""
        result = self.exportStandaloneResults(format_type)
        if result:
            return result
        return ""

    @pyqtSlot(result=str)
    def saveResults(self):
        """Save current processing results - callable from UI"""
        result = self.saveStandaloneResults("manual_save")
        if result:
            return result
        return ""

    @pyqtSlot(result=str)
    def loadResults(self):
        """Load previously saved results - callable from UI"""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Load Saved Results",
            self.log_local_path,
            "Numpy Archive Files (*.npz);;All Files (*)"
        )
        if file_path:
            result = self.loadSavedResults(file_path)
            if result:
                return file_path
        return ""

    @pyqtSlot(str, result='bool')
    def setStandaloneFile(self, file_path):
        """Set the standalone file path for HTML file input selections"""
        if file_path and os.path.exists(file_path):
            self.standalone_file_path = file_path
            self.showNotification.emit(f"File ready: {os.path.basename(file_path)}", "success")
            return True
        else:
            self.showNotification.emit("File path is invalid or file does not exist", "error")
            return False
        return model_name


class TreeAIBoxWeb(QMainWindow):
    def __init__(self):
        super().__init__()
                
        self.setWindowTitle("TreeAIBox")
        self.resize(1200, 900)

        # Create web view
        self.web_view = WebEnginePage(self)
        self.setCentralWidget(self.web_view)

        # Set up web channel for JavaScript communication
        self.channel = QWebChannel()
        self.web_interface = WebInterface(self)
        self.channel.registerObject("backend", self.web_interface)
        self.web_view.page().setWebChannel(self.channel)

        # Load HTML content
        self.loadHtmlContent()



    def closeEvent(self, event):
        """Handle window close event with proper cleanup"""

        if hasattr(self.web_interface, 'workers'):
            for worker in self.web_interface.workers:
                if worker.isRunning():
                    worker.terminate()
                    worker.wait(3000)  # Wait up to 3 seconds
            self.web_interface.workers.clear()
        
        # Clear the global reference
        app = QApplication.instance()
        if app is not None:
        #     print("Forcing application exit...")
            app.quit()
            QApplication.exit()

        # Accept the close event
        #event.accept()
        #super().closeEvent(event)


    def loadHtmlContent(self):
        """Load the HTML UI"""
        # Get the current directory
        current_dir = os.path.dirname(os.path.realpath(__file__))
        html_path = os.path.join(current_dir, "treeaibox_ui.html")

        if os.path.exists(html_path):
            self.web_view.load(QUrl.fromLocalFile(html_path))
        else:
            # If HTML file not found, create a simple HTML content with error message
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>TreeAIBox</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .error { color: red; font-weight: bold; }
                </style>
            </head>
            <body>
                <h1>TreeAIBox</h1>
                <p class="error">Error: UI file not found.</p>
                <p>Please ensure that the treeaibox_ui.html file is in the same directory as this application.</p>
            </body>
            </html>
            """
            self.web_view.setHtml(html_content)



if __name__ == "__main__":
    # Get existing QApplication instance or create new one if none exists
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        
    window = TreeAIBoxWeb()
    window.show()
    sys.exit(app.exec())