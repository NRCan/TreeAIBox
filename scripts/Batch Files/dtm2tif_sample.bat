@echo off
REM Check if DTM file exists
IF NOT EXIST "LLY\Output\ground.dtm" (
    echo DTM file not found: LLY\Output\ground.dtm
    exit /b 1
)

REM Convert DTM to georeferenced TIFF using DTM2TIF
REM Output: ground.tif and ground.tfw
..\DTM2TIF.exe LLY\Output\ground.dtm

echo DTM to TIFF conversion complete. Script: dtm2tif_sample.bat
