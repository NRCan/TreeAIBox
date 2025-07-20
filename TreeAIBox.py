import sys
import os
import json
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
except ImportError:
    PYCC_AVAILABLE = False
    print("Warning: PyCC not available. Some functionality will be limited.")


# Add this helper class to process events during long operations
class ProcessEvents:
    def __init__(self, msec=100):
        self.msec = msec
        self.last_time = 0

    def __call__(self, progress):
        # Process events periodically to keep UI responsive
        current_time = QApplication.instance().startTimer(0)
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
            self.showNotification.emit("CloudCompare API not available", "error")
            return False
        if not CC.haveSelection():
            self.showNotification.emit("Please select at least one point cloud to proceed", "warning")
            return False
        return True

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





    @pyqtSlot(bool, str, bool,str, result=bool)
    def compFilter(self, use_gpu, component_type, if_bottom_only=False,subfolder="filter"):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Apply component filtering called with use_gpu={use_gpu}, component_type={component_type}")
        print(f"Currently selected model: {self.selected_model}")

        if not self.checkSelection():
            return False

        try:
            # Get selected entities
            pcs = CC.getSelectedEntities()

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
            CC.redrawAll()
            CC.updateUI()

            self.showNotification.emit(f"TreeFilter processing completed for {pc.getName()}", "success")

        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
            self.progressUpdated.emit(0)

    @pyqtSlot(float, int, result=bool)
    def applyNoiseClean(self,max_gap=3.0,min_pts=100):
        if not self.checkSelection():
            return False

        pcs = CC.getSelectedEntities()

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
            pcs = CC.getSelectedEntities()
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
                dtm_pcd = pycc.ccPointCloud(f"{pc.getName()}_dtm")
                for dtm_pt in dtm:
                    dtm_pcd.addPoint(cccorelib.CCVector3(dtm_pt[0], dtm_pt[1], dtm_pt[2]))

                self.progressUpdated.emit(100)

                pc.addChild(dtm_pcd)
                CC.addToDB(dtm_pcd)
                CC.redrawAll()
                CC.updateUI()
            return True
        except Exception as e:
            self.showNotification.emit(f"Error in DTM creation: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    @pyqtSlot(bool, bool, float,float, float, float, float, float, float, result=bool)
    def treeLoc(self, use_gpu, if_stem, cutoff_thresh, conf_thresh, min_rad, max_gap, nms_thresh,custom_voxel_res_xy,custom_voxel_res_z):
        """Apply component filtering to the selected point cloud using 3D deep learning"""
        print(f"Apply TreeLoc extraction with use_gpu={use_gpu}")
        print(f"Currently selected model: {self.selected_model}")

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

                if len(pcd)<10000:
                    response = QMessageBox.question(None, "Confirmation Required", f"The point cloud has only {len(pcd)}. Make sure you select the correct point cloud(s). Do you want to continue?",
                                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if response != QMessageBox.StandardButton.Yes:
                        self.showNotification.emit("Operation cancelled by user", "info")
                        return False

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
                if not self.checkModelExistence(model_path, model_name):
                    return False

                # Import DL filter module
                from modules.treeisonet.treeLoc import treeLoc

                self.progressUpdated.emit(5)

                # Check for tree filter field
                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    pcd_abg = pcd[treefilter_ind]
                else:
                    pcd_abg = pcd
                    treefilter_ind = None

                if if_stem:
                    stemcls_field = pc.getScalarFieldIndexByName("stemcls")
                    if stemcls_field < 0:  # ccPointCloud(point cloud),ccHObject(grouped)
                        self.showNotification.emit("Please extract stems points by running stemcls first", "warning")
                        self.progressUpdated.emit(0)
                        return False
                    stemcls = np.array(pc.getScalarField(stemcls_field).asArray()).astype(np.int32)
                    if treefilter_field >= 0:
                        stemcls=stemcls[treefilter_ind]
                    pcd_abg=pcd_abg[stemcls>1]

                # Create and configure the worker
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
                self.workers.append(worker)
                worker.start()

                return True

        except Exception as e:
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
            # Create location point cloud
            loc_pcd = pycc.ccPointCloud(f"{pc.getName()}_loc")
            self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treeloc_tops))}", "error")

            for treeloc_top in pred_treeloc_tops:
                loc_pcd.addPoint(cccorelib.CCVector3(treeloc_top[0], treeloc_top[1], treeloc_top[2]))

            loc_pcd.setPointSize(16)

            pc.addChild(loc_pcd)
            CC.addToDB(loc_pcd)

            # Update UI
            CC.redrawAll()
            CC.updateUI()

            self.showNotification.emit(f"TreeLoc processing completed for {pc.getName()}", "success")

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

            # Create location point cloud
            loc_pcd = pycc.ccPointCloud(f"{pc.getName()}_loc")
            self.showNotification.emit(f"Number of tree locations extracted: {str(len(pred_treelocs))}", "error")

            for pred_treeloc in pred_treelocs:
                loc_pcd.addPoint(cccorelib.CCVector3(pred_treeloc[0], pred_treeloc[1], pred_treeloc[2]))

            loc_pcd.setPointSize(16)

            pc.addChild(loc_pcd)
            CC.addToDB(loc_pcd)

            # Update UI
            CC.redrawAll()
            CC.updateUI()

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
            pcs = CC.getSelectedEntities()
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

            CC.redrawAll()
            CC.updateUI()

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
            pcs = CC.getSelectedEntities()
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
            CC.redrawAll()
            CC.updateUI()

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
            # Get selected entities
            pcs = CC.getSelectedEntities()

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
                # Get selected model
                if not self.selected_model:
                    self.showNotification.emit("No model selected", "error")
                    return False

                # Import DL filter module
                # current_script_path = os.path.dirname(os.path.realpath(__file__))
                # sys.path.append(current_script_path)
                from modules.treeisonet.crownOff import crownOff
                # Set progress to 0%
                self.progressUpdated.emit(5)

                itc_field = pc.getScalarFieldIndexByName(f"stemoff")
                if itc_field < 0:
                    self.showNotification.emit("Please apply the StemClustering SP first", "warning")
                    self.progressUpdated.emit(0)
                    return
                stem_id = np.array(pc.getScalarField(itc_field).asArray()).astype(np.int32)

                treefilter_field = pc.getScalarFieldIndexByName("treefilter")
                if treefilter_field >= 0:
                    treefilter = np.array(pc.getScalarField(treefilter_field).asArray()).astype(np.int32)
                    treefilter_ind = treefilter > 1.0
                    pcd_abg = pcd[treefilter_ind]
                    stem_id=stem_id[treefilter_ind]
                else:
                    pcd_abg = pcd
                    treefilter_ind = None

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
                worker.finished.connect(lambda success, preds: self._handle_crownoff_result(success, preds, pc,treefilter_ind))
                worker.errorOccurred.connect(lambda error: self.showNotification.emit(f"Error in crownoff processing: {error}", "error"))

                # Keep a reference to the worker
                self.workers.append(worker)
                worker.start()

                return True

        except Exception as e:
            self.showNotification.emit(f"Error in crownoff processing: {str(e)}", "error")
            self.progressUpdated.emit(0)
            return False

    def _handle_crownoff_result(self, success, preds, pc,treefilter_ind):
        """Handle the results from the worker thread for crownOff"""
        if not success or preds is None:
            return
        self.progressUpdated.emit(100)
        try:
            # Process the results
            pred_treeitc = np.zeros(len(pc.points()), dtype=np.int32)
            if treefilter_ind is not None:
                pred_treeitc[treefilter_ind] = preds
            else:
                pred_treeitc = preds
            # Update CloudCompare scalar field
            labels_field = pc.getScalarFieldIndexByName("itc")
            if labels_field < 0:
                labels_field = pc.addScalarField("itc")

            sfArray = pc.getScalarField(labels_field).asArray()
            sfArray[:] = pred_treeitc
            pc.getScalarField(labels_field).computeMinAndMax()
            pc.setCurrentDisplayedScalarField(labels_field)
            pc.showSF(True)

            # Update UI
            CC.redrawAll()
            CC.updateUI()

            self.showNotification.emit(f"CrownOff processing completed for {pc.getName()}", "success")

        except Exception as e:
            self.showNotification.emit(f"Error updating results: {str(e)}", "error")
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
            pcs = CC.getSelectedEntities()

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
                CC.redrawAll()
                CC.updateUI()

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
            pcs = CC.getSelectedEntities()

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

                # Apply QSM
                tree, segs_centroids, segs_labels, tree_centroid_radius = applyQSM.applyQSM(
                    pcd_with_class,
                    max_connectivity_search_distance=gap_connectivity,
                    occlusion_distance_cutoff=max_gap,
                    progress_callback=lambda p: self.progressUpdated.emit(p)
                )

                # Create branch medial structure in CloudCompare
                pcd_wrapper = pycc.ccHObject(f"{pc.getName()}_branch_medial")

                for i, branch in enumerate(tree):
                    branch_medial_pcd = pycc.ccPointCloud(f"{pc.getName()}_branch_medial")

                    for node in branch:
                        branch_medial_pcd.addPoint(cccorelib.CCVector3(
                            segs_centroids[node][0],
                            segs_centroids[node][1],
                            segs_centroids[node][2]
                        ))

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

                # Save tree structure to OBJ and XML files
                obj_path = os.path.join(self.log_local_path, f"{pc.getName()}_woodobj.obj")
                xml_path = os.path.join(self.log_local_path, f"{pc.getName()}_wood.xml")

                applyQSM.saveTreeToObj(tree_centroid_radius, obj_path)
                applyQSM.saveTreeToXML(tree, tree_centroid_radius, xml_path)

                self.progressUpdated.emit(90)

                # Load the OBJ file into CloudCompare
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
                CC.redrawAll()
                CC.updateUI()

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

        # Accept the close event
        # event.accept()
        # super().closeEvent(event)

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
    else:
        window = TreeAIBoxWeb()
        window.show()
