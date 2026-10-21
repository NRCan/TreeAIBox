@echo off
REM Run CloudMetrics on all stand LAS files and output metrics to CSV
REM Processes all stand_*.las files in the output folder

REM Check if CloudMetrics.exe exists in the parent directory
IF NOT EXIST "..\CloudMetrics.exe" (
    echo CloudMetrics.exe not found in the parent directory.
    exit /b 1
)


REM Run CloudMetrics with DTM for height normalization
..\CloudMetrics.exe /new /id /ground:..\Data\LLY\Output\ground.dtm ..\Data\LLY\Output\stand_*.las ..\Data\LLY\Output\stand_metrics.csv

REM Check errorlevel and report success/failure
IF %ERRORLEVEL% NEQ 0 (
    echo CloudMetrics failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
) else (
    echo CloudMetrics completed successfully.
)
