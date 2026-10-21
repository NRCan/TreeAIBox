@echo off
REM Check if input LAS file exists
IF NOT EXIST "LLY\Airborne\20241009144557_AGRG_LLR_Topo_CGVD2013.las" (
    echo Input LAS file not found: LLY\Airborne\20241009144557_AGRG_LLR_Topo_CGVD2013.las
    exit /b 1
)

REM Step: Filter ground points from raw LAS file using GroundFilter
REM Output: ground_points.las
REM Example with cell size 10.0 meters:
..\GroundFilter.exe LLY\Output\ground_points.las 10.0 LLY\Airborne\20241009144557_AGRG_LLR_Topo_CGVD2013.las

REM You can add parameters like /gparam, /wparam, /iterations as needed, e.g.:
REM ..\GroundFilter.exe /gparam:0 /wparam:0.5 /iterations:8 LLY\Output\ground_points.las 10.0 LLY\Airborne\20241009144557_AGRG_LLR_Topo_CGVD2013.las

echo Ground points file generation complete. Script: groundfilter_sample.bat
