@echo off
REM Script to run PolyClipData with Plot_Buffer_11m.shp polygons
REM Clips LAS data using polygons from Plot_Buffer_11m.shp

REM Check if PolyClipData.exe exists in the current directory
IF NOT EXIST "..\PolyClipData.exe" (
    echo PolyClipData.exe not found in the parent directory.
    exit /b 1
)

REM Run PolyClipData with provided arguments
..\PolyClipData.exe /multifile /shape:1,* ..\Data\LLY\Plot_Polygon\Plot_Buffer_11m.shp ..\Data\LLY\Output\stand.las ..\Data\LLY\Airborne\20241009144557_AGRG_LLR_Topo_CGVD2013.las

REM Check errorlevel and report success/failure
IF %ERRORLEVEL% NEQ 0 (
    echo PolyClipData failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
) else (
    echo PolyClipData completed successfully.
)
