; TreeAIBox - CloudCompare Python Plugin Installer
; NSIS Script for creating a GUI installer

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "nsDialogs.nsh"

; General Settings
Name "TreeAIBox Plugin for CloudCompare"
OutFile "TreeAIBox_Plugin_Installer.exe"
Unicode True
RequestExecutionLevel admin
InstallDir "$PROGRAMFILES\CloudCompare"

; Variables
Var CCPath
Var PythonPath
Var CCPathPage
Var CCPathText
Var CCPathBrowseButton
Var InstallStatusText
Var CCPathFound
Var PythonPathFound
Var HasNvidiaGPU
Var GPUInfoText

; Interface Settings
!define MUI_ABORTWARNING
!define MUI_ICON "treeaibox_logo.ico"
!define MUI_UNICON "treeaibox_logo.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "treeaibox-header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "treeaibox-welcome.bmp"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
Page custom CCPathSelection CCPathSelectionLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Languages
!insertmacro MUI_LANGUAGE "English"

; Use existing license file
Function .onInit
    IfFileExists "LICENSE.txt" +3 0
    FileOpen $0 "LICENSE.txt" w
    FileWrite $0 "This plugin is provided as-is without any warranty.$\r$\n$\r$\nBy installing this plugin, you agree to use it at your own risk."
    FileClose $0
    
    ; Initialize variables
    StrCpy $CCPathFound "0"
    StrCpy $PythonPathFound "0"
    StrCpy $HasNvidiaGPU "0"
    
    ; Check for Nvidia GPU
    DetailPrint "Checking for NVIDIA GPU..."
    
    ; Create a temporary batch file to check for NVIDIA GPU
    FileOpen $0 "$TEMP\check_nvidia.bat" w
    FileWrite $0 '@echo off$\r$\n'
    FileWrite $0 'wmic path win32_VideoController get name | findstr /i "NVIDIA" > nul$\r$\n'
    FileWrite $0 'if %ERRORLEVEL% EQU 0 ($\r$\n'
    FileWrite $0 '  echo NVIDIA GPU found$\r$\n'
    FileWrite $0 '  exit 0$\r$\n'
    FileWrite $0 ') else ($\r$\n'
    FileWrite $0 '  echo No NVIDIA GPU found$\r$\n'
    FileWrite $0 '  exit 1$\r$\n'
    FileWrite $0 ')$\r$\n'
    FileClose $0
    
    ; Run the batch file and capture result
    nsExec::ExecToStack '"$TEMP\check_nvidia.bat"'
    Pop $0 ; Return value
    Pop $1 ; Output
    
    ; Set the GPU flag based on result
    ${If} $0 == "0"
        StrCpy $HasNvidiaGPU "1"
        DetailPrint "NVIDIA GPU detected"
    ${Else}
        DetailPrint "No NVIDIA GPU detected"
    ${EndIf}
    
    ; Clean up
    Delete "$TEMP\check_nvidia.bat"
    
    ; Try to find CloudCompare installation
    FindCloudCompare:
    ; Check common installation paths

    IfFileExists "C:\Program Files\CloudCompare\CloudCompare.exe" 0 +2
    StrCpy $CCPath "C:\Program Files\CloudCompare"

    IfFileExists "$PROGRAMFILES\CloudCompare\CloudCompare.exe" 0 +2
    StrCpy $CCPath "$PROGRAMFILES\CloudCompare"
    
    IfFileExists "$PROGRAMFILES32\CloudCompare\CloudCompare.exe" 0 +2
    StrCpy $CCPath "$PROGRAMFILES32\CloudCompare"
    
    IfFileExists "$LOCALAPPDATA\Programs\CloudCompare\CloudCompare.exe" 0 +2
    StrCpy $CCPath "$LOCALAPPDATA\Programs\CloudCompare"
    
    ; Check in Registry
    ReadRegStr $0 HKLM "SOFTWARE\CloudCompare" "InstallPath"
    ${If} $0 != ""
        IfFileExists "$0\CloudCompare.exe" 0 +2
        StrCpy $CCPath "$0"
    ${EndIf}
    
    ; Check if CloudCompare was found
    ${If} $CCPath != ""
        StrCpy $CCPathFound "1"
    ${EndIf}
    
    ; Check if Python exists in the found CloudCompare path
    ${If} $CCPathFound == "1"
        IfFileExists "$CCPath\plugins\Python\python.exe" 0 +2
        StrCpy $PythonPathFound "1"
        StrCpy $PythonPath "$CCPath\plugins\Python\python.exe"
    ${EndIf}
FunctionEnd

; Custom page to select CloudCompare path
Function CCPathSelection
    !insertmacro MUI_HEADER_TEXT "CloudCompare Location" "Select the folder where CloudCompare is installed."
    
    nsDialogs::Create 1018
    Pop $CCPathPage
    
    ${NSD_CreateLabel} 0 0 100% 24u "Select the location of your CloudCompare installation:"
    Pop $0
    
    ${NSD_CreateText} 0 30u 70% 12u $CCPath
    Pop $CCPathText
    
    ${NSD_CreateBrowseButton} 72% 30u 28% 12u "Browse..."
    Pop $CCPathBrowseButton
    ${NSD_OnClick} $CCPathBrowseButton CCPathBrowse
    
    ${If} $CCPathFound == "1"
        ${NSD_CreateLabel} 0 50u 100% 12u "CloudCompare installation found at: $CCPath"
    ${Else}
        ${NSD_CreateLabel} 0 50u 100% 12u "CloudCompare installation not found automatically. Please select manually."
    ${EndIf}
    Pop $0
    
    ${If} $PythonPathFound == "1"
        ${NSD_CreateLabel} 0 70u 100% 12u "Python found at: $PythonPath"
    ${Else}
        ${NSD_CreateLabel} 0 70u 100% 24u "Python not found in the CloudCompare plugins directory. The installer will continue, but Python must be installed for the plugin to work."
    ${EndIf}
    Pop $InstallStatusText
    
    ; Display GPU information
    ${If} $HasNvidiaGPU == "1"
        ${NSD_CreateLabel} 0 100u 100% 36u "NVIDIA GPU detected. The installer will use the CUDA-enabled version of PyTorch, which offers better performance for machine learning tasks."
    ${Else}
        ${NSD_CreateLabel} 0 100u 100% 36u "No NVIDIA GPU detected. The installer will use the CPU version of PyTorch. Processing may be slower for machine learning tasks."
    ${EndIf}
    Pop $GPUInfoText
    
    nsDialogs::Show
FunctionEnd

Function CCPathBrowse
    ${NSD_GetText} $CCPathText $0
    nsDialogs::SelectFolderDialog "Select CloudCompare Folder" $0
    Pop $0
    ${If} $0 != error
        StrCpy $CCPath $0
        ${NSD_SetText} $CCPathText $0
        
        ; Verify if this is a valid CloudCompare installation
        IfFileExists "$CCPath\CloudCompare.exe" 0 InvalidCC
        
        ; Valid CloudCompare, check Python
        IfFileExists "$CCPath\plugins\Python\python.exe" 0 NoPython
        
        ; Python found
        StrCpy $PythonPathFound "1"
        StrCpy $PythonPath "$CCPath\plugins\Python\python.exe"
        ${NSD_SetText} $InstallStatusText "CloudCompare and Python found successfully!"
        Goto Done
        
        NoPython:
        StrCpy $PythonPathFound "0"
        ${NSD_SetText} $InstallStatusText "CloudCompare found, but Python is missing. The plugin will not work correctly."
        Goto Done
        
        InvalidCC:
        ${NSD_SetText} $InstallStatusText "Invalid CloudCompare installation. CloudCompare.exe not found."
        
        Done:
    ${EndIf}
FunctionEnd

Function CCPathSelectionLeave
    ${NSD_GetText} $CCPathText $CCPath
    
    ; Final validation before proceeding
    IfFileExists "$CCPath\CloudCompare.exe" +3 0
    MessageBox MB_ICONEXCLAMATION|MB_OK "CloudCompare.exe not found in the selected directory. Installation cannot continue."
    Abort
    
    ; Update Python path based on CC path
    StrCpy $PythonPath "$CCPath\plugins\Python\python.exe"
    IfFileExists "$PythonPath" +3 0
    MessageBox MB_ICONEXCLAMATION|MB_YESNO "Python not found in the CloudCompare plugins directory. The plugin may not work correctly. Do you want to continue anyway?" IDYES +2
    Abort
FunctionEnd

Section "Install Python Packages" SecInstall
    SetOutPath "$CCPath\plugins\Python"
    
    ; Create a temporary batch file to install packages
    FileOpen $0 "$TEMP\install_packages.bat" w
    FileWrite $0 '@echo off$\r$\n'
    FileWrite $0 'echo Installing Python packages...$\r$\n'
    FileWrite $0 '"$PythonPath" -m pip install --upgrade pip$\r$\n'
    
    ; Install PyTorch based on GPU detection
    ${If} $HasNvidiaGPU == "1"
        DetailPrint "Installing CUDA-enabled PyTorch..."
        FileWrite $0 'echo Installing CUDA-enabled PyTorch...$\r$\n'
        FileWrite $0 '"$PythonPath" -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121$\r$\n'
    ${Else}
        DetailPrint "Installing CPU-only PyTorch..."
        FileWrite $0 'echo Installing CPU-only PyTorch...$\r$\n'
        FileWrite $0 '"$PythonPath" -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu$\r$\n'
    ${EndIf}
    
    ; Install other required packages
    FileWrite $0 'echo Installing other required packages...$\r$\n'
    FileWrite $0 '"$PythonPath" -m pip install PyQt6 PyQt6-WebEngine requests numpy_indexed timm numpy_groupies cut_pursuit_py circle_fit scikit-learn$\r$\n'
    FileWrite $0 'if %ERRORLEVEL% NEQ 0 ($\r$\n'
    FileWrite $0 '  echo Installation failed with error code %ERRORLEVEL%$\r$\n'
    FileWrite $0 '  exit /b %ERRORLEVEL%$\r$\n'
    FileWrite $0 ')$\r$\n'
    FileWrite $0 'echo Installation successful$\r$\n'
    FileClose $0
    
    ; Run the batch file and capture output
    DetailPrint "Installing required Python packages..."
    nsExec::ExecToLog '"$TEMP\install_packages.bat"'
    Pop $0
    
    ; Check result
    ${If} $0 != "0"
        DetailPrint "Package installation failed with exit code $0"
        MessageBox MB_ICONEXCLAMATION|MB_OK "Failed to install required Python packages. Please check the log for details."
    ${Else}
        DetailPrint "Python packages installed successfully"
    ${EndIf}
    
    ; Clean up
    Delete "$TEMP\install_packages.bat"
    
    ; Create TreeAIBox directory structure in the plugins folder
    DetailPrint "Installing TreeAIBox plugin..."
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox"
    
    ; Copy main plugin files
    File "TreeAIBox.py"
    File "model_zoo.json"
    File "treeaibox_ui.html"
    File "dl_visualization.svg"
    
    ; Create and copy img directory
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\img"
    File /nonfatal "img\*.png"
    File /nonfatal "img\*.jpg"
    File /nonfatal "img\*.svg"
    
    ; Create and copy modules directory
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\filter"
    File /nonfatal "modules\filter\*.py"
    File /nonfatal "modules\filter\*.json"
    
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\qsm"
    File /nonfatal "modules\qsm\*.py"
    
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\treeisonet"
    File /nonfatal "modules\treeisonet\*.py"
    File /nonfatal "modules\treeisonet\*.json"
    
    DetailPrint "Installation complete"
SectionEnd