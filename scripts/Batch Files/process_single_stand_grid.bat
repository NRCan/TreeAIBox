@echo off
setlocal
REM This batch file processes a single stand LAS file with GridMetrics
set STAND_FILE_NO_EXT=%~n1
set STAND_FILE_FULL_NAME=%1
REM Define your ground model path, heightbreak, and cellsize
set GROUND_MODEL=LLY\DTM\ground.dtm
set HEIGHT_BREAK=1.37
set CELL_SIZE=15.0
set OUTPUT_BASE_NAME=%STAND_FILE_NO_EXT%_gridmetrics
REM Run GridMetrics for this stand
..\GridMetrics.exe "%GROUND_MODEL%" %HEIGHT_BREAK% %CELL_SIZE% "%OUTPUT_BASE_NAME%" "%STAND_FILE_FULL_NAME%" ^
    /raster:mean,cover,p90 /ascii /minht:0.0
IF ERRORLEVEL 1 (
    echo Error processing %STAND_FILE_FULL_NAME%
) ELSE (
    echo Successfully processed %STAND_FILE_FULL_NAME%
)
endlocal
