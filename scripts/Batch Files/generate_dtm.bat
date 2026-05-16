


@echo off
REM Check if ground points LAS file exists
IF NOT EXIST "LLY\Output\ground_points.las" (
    echo Ground points LAS file not found: LLY\Output\ground_points.las
    exit /b 1
)

REM Step: Create DTM from classified ground points using GridSurfaceCreate
REM Output: ground.dtm
REM Example parameters: cell size 10.0 meters, units meters, UTM zone 20N, NAD83 datum
..\GridSurfaceCreate.exe LLY\Output\ground.dtm 10.0 M M 1 20 1 0 LLY\Output\ground_points.las

REM You can add parameters to GridSurfaceCreate as needed, e.g. /maximum, /filldist:#

echo DTM generation complete. Script: generate_dtm.bat
