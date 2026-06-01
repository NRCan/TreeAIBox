; TreeAIBox - CloudCompare Python Plugin Installer
; NSIS Script for creating a GUI installer with reinstallation support

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
Var IsReinstall

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

; String contains macro
!macro StrContains ResultVar String SubString
  Push `${String}`
  Push `${SubString}`
  Call StrContains
  Pop `${ResultVar}`
!macroend
!define StrContains "!insertmacro StrContains"

; Function to kill processes that might lock files
Function KillProcesses
    DetailPrint "Checking for running CloudCompare processes..."
    
    ; Kill CloudCompare processes
    nsExec::ExecToStack 'taskkill /F /IM "CloudCompare.exe" /T'
    Pop $0
    ${If} $0 == "0"
        DetailPrint "CloudCompare processes terminated"
        Sleep 2000  ; Wait for processes to fully terminate
    ${Else}
        DetailPrint "No CloudCompare processes found or already terminated"
    ${EndIf}
    
    ; Kill any Python processes that might be using the plugin files
    nsExec::ExecToStack 'taskkill /F /IM "python.exe" /FI "WINDOWTITLE eq *TreeAIBox*" /T'
    Pop $0
    DetailPrint "Python processes check completed"
FunctionEnd

; Function to check if TreeAIBox is already installed
Function CheckExistingInstallation
    Push $R0
    
    StrCpy $IsReinstall "0"
    
    ; Check if TreeAIBox plugin already exists
    ${If} ${FileExists} "$CCPath\plugins\Python\Plugins\TreeAIBox\TreeAIBox.py"
        StrCpy $IsReinstall "1"
        DetailPrint "Existing TreeAIBox installation detected"
        
        ; Show confirmation dialog for reinstallation
        MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 \
            "TreeAIBox plugin is already installed in this CloudCompare installation.$\r$\n$\r$\nDo you want to reinstall it?" \
            IDYES ContinueReinstall
        
        ; User chose No - return to previous page instead of quitting
        DetailPrint "User cancelled reinstallation"
        StrCpy $IsReinstall "0"  ; Reset reinstall flag
        Abort  ; This will abort the current page and return to previous page
        
        ContinueReinstall:
        DetailPrint "User confirmed reinstallation"
    ${EndIf}
    
    Pop $R0
FunctionEnd

; Function to backup existing installation (removed - no longer used)
; Backup functionality removed per user request

; Try to find CloudCompare installation
Function FindCloudCompare
    Push $R0
    Push $R1
    Push $R2
    
    DetailPrint "Searching for CloudCompare..."
    
    ; Initialize variables
    StrCpy $CCPathFound "0"
    StrCpy $PythonPathFound "0"
    
    ; Method 1: Check CloudCompare Python Runtime Settings - For users who have used the plugin before
    DetailPrint "Checking Python Runtime Settings in registry..."
    ReadRegStr $0 HKCU "SOFTWARE\CCCorp\CloudCompare:PythonRuntime.Settings" "EnvPath"
    ${If} $0 != ""
        DetailPrint "Found Python EnvPath: $0"
        ; EnvPath typically points to the Python folder inside CloudCompare plugins
        ${GetParent} $0 $1        ; Get plugins folder
        ${GetParent} $1 $2        ; Get CloudCompare folder
        
        ; Verify it's CloudCompare
        IfFileExists "$2\CloudCompare.exe" 0 Check_Registry
        StrCpy $CCPath $2
        StrCpy $CCPathFound "1"
        
        StrCpy $PythonPath "$0\python.exe"
        IfFileExists "$PythonPath" 0 Check_Python
        StrCpy $PythonPathFound "1"
        DetailPrint "Python found at: $PythonPath"
        Goto Finish
    ${EndIf}
    
    Check_Registry:
    ; Method 2: Check Uninstall registry entries
    DetailPrint "Checking Uninstall registry entries..."
    StrCpy $R0 "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    
    ; Enumerate all subkeys to find CloudCompare
    StrCpy $R1 0
    
    Registry_Loop:
        EnumRegKey $R2 HKLM $R0 $R1
        StrCmp $R2 "" Check_Standard_Paths
        IntOp $R1 $R1 + 1
        
        ; Check if this entry contains "_is1" (typical for InnoSetup installers like CloudCompare)
        ${StrContains} $1 "_is1" $R2
        ${If} $1 != "-1"
            ; Read the DisplayIcon value to find the path
            ReadRegStr $0 HKLM "$R0\$R2" "DisplayIcon"
            ${If} $0 != ""
                ; DisplayIcon typically contains the full path to the executable with parameters
                ; We need to extract just the path
                ${GetParent} $0 $1
                
                ; Verify it's CloudCompare
                IfFileExists "$1\CloudCompare.exe" 0 Registry_Loop
                StrCpy $CCPath $1
                StrCpy $CCPathFound "1"
                DetailPrint "CloudCompare found at: $CCPath"
                Goto Check_Python
            ${EndIf}
        ${EndIf}
        
        ; Check if DisplayName contains "CloudCompare"
        ReadRegStr $0 HKLM "$R0\$R2" "DisplayName"
        ${If} $0 != ""
            ${StrContains} $1 "CloudCompare" $0
            ${If} $1 != "-1"
                ; This entry is for CloudCompare, now get the install location
                ReadRegStr $0 HKLM "$R0\$R2" "InstallLocation"
                ${If} $0 != ""
                    ; Verify it's CloudCompare
                    IfFileExists "$0\CloudCompare.exe" 0 Registry_Loop
                    StrCpy $CCPath $0
                    StrCpy $CCPathFound "1"
                    DetailPrint "CloudCompare found at: $CCPath"
                    Goto Check_Python
                ${EndIf}
            ${EndIf}
        ${EndIf}
        
        Goto Registry_Loop
    
    Check_Standard_Paths:
    ; Method 3: Try standard paths as fallback
    DetailPrint "Checking standard installation paths..."
    
    ${If} ${FileExists} "C:\Program Files\CloudCompare\CloudCompare.exe"
        StrCpy $CCPath "C:\Program Files\CloudCompare"
        StrCpy $CCPathFound "1"
    ${ElseIf} ${FileExists} "$PROGRAMFILES\CloudCompare\CloudCompare.exe"
        StrCpy $CCPath "$PROGRAMFILES\CloudCompare"
        StrCpy $CCPathFound "1"
    ${ElseIf} ${FileExists} "E:\CloudCompare\CloudCompare.exe"
        StrCpy $CCPath "E:\CloudCompare"
        StrCpy $CCPathFound "1"
    ${EndIf}
    
    ${If} $CCPathFound == "1"
        DetailPrint "CloudCompare found at: $CCPath (from standard path)"
    ${Else}
        DetailPrint "CloudCompare not found automatically"
        Goto Finish
    ${EndIf}
    
    Check_Python:
    ; Check for Python in CloudCompare
    StrCpy $PythonPath "$CCPath\plugins\Python\python.exe"
    IfFileExists "$PythonPath" 0 Finish
    StrCpy $PythonPathFound "1"
    DetailPrint "Python found at: $PythonPath"
    
    Finish:
    Pop $R2
    Pop $R1
    Pop $R0
FunctionEnd

; Use existing license file or create a basic one
Function .onInit
    IfFileExists "LICENSE.txt" +3 0
    FileOpen $0 "LICENSE.txt" w
    FileWrite $0 "This plugin is provided as-is without any warranty.$\r$\n$\r$\nBy installing this plugin, you agree to use it at your own risk."
    FileClose $0
    
    ; Initialize variables
    StrCpy $CCPathFound "0"
    StrCpy $PythonPathFound "0"
    StrCpy $HasNvidiaGPU "0"
    StrCpy $IsReinstall "0"
    
    ; Check for Nvidia GPU
    DetailPrint "Checking for NVIDIA GPU..."
    
    ; Create a temporary batch file to check for NVIDIA GPU
    FileOpen $0 "$TEMP\check_nvidia.bat" w
    FileWrite $0 '@echo off$\r$\n'
    FileWrite $0 'wmic path win32_VideoController get name | findstr /i "NVIDIA" > nul$\r$\n'
    FileWrite $0 'if %ERRORLEVEL% EQU 0 (exit 0) else (exit 1)$\r$\n'
    FileClose $0
    
    ; Run the batch file and capture result
    nsExec::ExecToStack '"$TEMP\check_nvidia.bat"'
    Pop $0 ; Return value
    
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
    Call FindCloudCompare
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
    
    ; Check for existing installation
    Call CheckExistingInstallation
FunctionEnd

Function StrContains
  Exch $R1 ; SubString
  Exch
  Exch $R2 ; String
  Push $R3
  Push $R4
  Push $R5
  
  StrLen $R3 $R1 ; Length of SubString
  StrCpy $R4 0
  
  loop:
    StrCpy $R5 $R2 $R3 $R4 ; Copy part of String
    StrCmp $R5 $R1 done ; If equal to SubString, done
    StrCmp $R5 "" done ; If at end of String, done
    IntOp $R4 $R4 + 1 ; Increase offset
    Goto loop
  
  done:
    StrCmp $R5 "" notFound ; If at end of String, not found
    StrCpy $R0 $R4 ; Return position
    Goto return
  
  notFound:
    StrCpy $R0 -1 ; Return -1 if not found
  
  return:
    Pop $R5
    Pop $R4
    Pop $R3
    Pop $R1
    Exch $R0 ; Return value on stack
    Exch
    Pop $R2
FunctionEnd

; Function to convert backslashes to forward slashes
Function ConvertToForwardSlashes
    Exch $R0 ; get the path
    Push $R1
    Push $R2
    
    StrCpy $R1 0
    
    loop:
        StrCpy $R2 $R0 1 $R1
        StrCmp $R2 "" done
        StrCmp $R2 "\" replaceChar
        IntOp $R1 $R1 + 1
        Goto loop
    
    replaceChar:
        StrCpy $R2 $R0 $R1
        IntOp $R1 $R1 + 1
        StrCpy $R0 "$R2/$R0" "" $R1
        Goto loop
    
    done:
        Pop $R2
        Pop $R1
        Exch $R0
FunctionEnd

Section "Install Python Packages" SecInstall
    ; Check for existing installation and handle accordingly
    ${If} $IsReinstall == "1"
        DetailPrint "Reinstalling TreeAIBox plugin..."
        
        ; Kill any running processes that might lock files
        Call KillProcesses
        
        ; Force remove existing installation directory (no backup)
        DetailPrint "Removing existing installation..."
        RMDir /r "$CCPath\plugins\Python\Plugins\TreeAIBox"
        
        ; Wait a bit to ensure file system operations complete
        Sleep 1000
    ${EndIf}
    
    SetOutPath "$CCPath\plugins\Python"
    
    ; Create a temporary batch file to install packages
    FileOpen $0 "$TEMP\install_packages.bat" w
    FileWrite $0 '@echo off$\r$\n'
    FileWrite $0 'echo Installing Python packages...$\r$\n'
    FileWrite $0 '"$PythonPath" -m pip install --upgrade pip$\r$\n'
    
    ; NOTE: --force-reinstall is essential. CloudCompare ships its own embedded
    ; Python, and a CloudCompare upgrade can change that Python's version (e.g.
    ; 3.10 -> 3.12). Without --force-reinstall, pip sees "torch==2.5.1 already
    ; installed" and SKIPS it, leaving wheels built for the OLD Python in place
    ; (they then fail to load). --force-reinstall replaces them with wheels
    ; matching the current embedded Python, so simply re-running this installer
    ; after a CloudCompare update repairs everything. Cached wheels are reused,
    ; so a re-run on the same Python version does not re-download.

    ; Install PyTorch based on GPU detection
    ${If} $HasNvidiaGPU == "1"
        DetailPrint "Installing CUDA-enabled PyTorch..."
        FileWrite $0 'echo Installing CUDA-enabled PyTorch...$\r$\n'
        FileWrite $0 '"$PythonPath" -m pip install --force-reinstall torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121$\r$\n'
    ${Else}
        DetailPrint "Installing CPU-only PyTorch..."
        FileWrite $0 'echo Installing CPU-only PyTorch...$\r$\n'
        FileWrite $0 '"$PythonPath" -m pip install --force-reinstall torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu$\r$\n'
    ${EndIf}

    ; Install other required packages (pinned to the validated set)
    FileWrite $0 'echo Installing other required packages...$\r$\n'
    FileWrite $0 '"$PythonPath" -m pip install --force-reinstall PyQt6==6.9.1 PyQt6-WebEngine==6.9.0 requests==2.32.4 numpy==1.26.4 numpy_indexed==0.3.7 numpy_groupies==0.11.3 timm==1.0.15 cut_pursuit_py==1.0.12 circle_fit==0.2.1 scikit-learn==1.6.1 scikit-image==0.25.2$\r$\n'
    FileWrite $0 'if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%$\r$\n'
    FileClose $0
    
    ; Run the batch file and capture output
    DetailPrint "Installing required Python packages..."
    nsExec::ExecToLog '"$TEMP\install_packages.bat"'
    Pop $0
    
    ; Check result
    ${If} $0 != "0"
        DetailPrint "Package installation failed with exit code $0"
        MessageBox MB_ICONEXCLAMATION|MB_OK "Failed to install required Python packages (Exit Code: $0).$\r$\n$\r$\nPlease check the detailed log above for specific error information.$\r$\n$\r$\nInstallation will be aborted so you can review the log and troubleshoot the issue."
        
        ; Abort installation to keep log visible
        Abort
    ${Else}
        DetailPrint "Python packages installed successfully"
    ${EndIf}
    
    ; Clean up
    Delete "$TEMP\install_packages.bat"
    
    ; Create TreeAIBox directory structure in the plugins folder
    DetailPrint "Installing TreeAIBox plugin files..."
    
    ; Ensure the main directory exists
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox"
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox"
    
    ; Set overwrite mode to force overwriting of existing files
    SetOverwrite on
    
    ; Copy main plugin files with forced overwrite
    File /oname=TreeAIBox.py "TreeAIBox.py"
    File /oname=model_zoo.json "model_zoo.json"
    File /oname=treeaibox_ui.html "treeaibox_ui.html"
    File /oname=dl_visualization.svg "dl_visualization.svg"
    File /oname=LICENSE.txt "LICENSE.txt"
    
    ; Create and copy directories with their contents
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox\img"
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\img"
    File /nonfatal "img\*.png"
    File /nonfatal "img\*.jpg"
    File /nonfatal "img\*.svg"
    
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox\modules"
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\filter"
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\filter"
    File /nonfatal "modules\filter\*.py"
    File /nonfatal "modules\filter\*.json"
    
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\qsm"
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\qsm"
    File /nonfatal "modules\qsm\*.py"
    
    CreateDirectory "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\treeisonet"
    SetOutPath "$CCPath\plugins\Python\Plugins\TreeAIBox\modules\treeisonet"
    File /nonfatal "modules\treeisonet\*.py"
    File /nonfatal "modules\treeisonet\*.json"
    
    ; Reset overwrite mode to default
    SetOverwrite ifnewer
    
    DetailPrint "Plugin files installation complete"
SectionEnd

Section "Register TreeAIBox Script" SecRegister
    DetailPrint "Registering TreeAIBox script with CloudCompare..."
    
    ; Get the script path with forward slashes for CloudCompare
    Push "$CCPath\plugins\Python\Plugins\TreeAIBox\TreeAIBox.py"
    Call ConvertToForwardSlashes
    Pop $R0
    
    DetailPrint "Script path: $R0"
    
    ; Check if file exists
    IfFileExists "$CCPath\plugins\Python\Plugins\TreeAIBox\TreeAIBox.py" +2 RegisterFailed
    DetailPrint "Script file found."
    
    ; Read existing registry value if it exists
    ReadRegStr $R1 HKCU "SOFTWARE\CCCorp\CloudCompare:PythonRuntime.Settings" "RegisterListPath"
    
    ${If} $R1 == ""
        ; No existing paths, just add our path
        WriteRegStr HKCU "SOFTWARE\CCCorp\CloudCompare:PythonRuntime.Settings" "RegisterListPath" "$R0"
        DetailPrint "Created new registry entry with path: $R0"
    ${Else}
        DetailPrint "Found existing registry value: $R1"
        
        ; Check if our path is already in the list
        ${StrContains} $R2 "$R0" "$R1"
        ${If} $R2 == "-1"
            ; Not found, append our path
            StrCpy $R1 "$R1;$R0"
            WriteRegStr HKCU "SOFTWARE\CCCorp\CloudCompare:PythonRuntime.Settings" "RegisterListPath" "$R1"
            DetailPrint "Added path to existing registry entry: $R1"
        ${Else}
            DetailPrint "Path already exists in registry"
        ${EndIf}
    ${EndIf}
    
    Goto RegisterEnd
    
    RegisterFailed:
    DetailPrint "Failed to register script - script file not found"
    MessageBox MB_ICONEXCLAMATION "Failed to register TreeAIBox script with CloudCompare. Script file not found."
    
    RegisterEnd:
SectionEnd