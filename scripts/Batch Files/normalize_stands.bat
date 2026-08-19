
@echo off
REM Create normalized folder if it doesn't exist
IF NOT EXIST "LLY\Output\normalized" (
    mkdir "LLY\Output\normalized"
)


REM Initialize counter
setlocal enabledelayedexpansion
set COUNT=1

REM First, rename all stand_*.las files with floating-point suffixes to integer-based names
for %%F in (LLY\Output\stand_*.las) do (
    echo %%~nF | findstr /r ".*[0-9]\.[0-9]+$" >nul
    if !ERRORLEVEL! EQU 0 (
        ren "%%F" "stand_!COUNT!.las"
        echo Renamed %%F to stand_!COUNT!.las
        set /a COUNT+=1
    )
)

REM Reset counter for normalization
set COUNT=1

REM Loop through all stand_*.las files in the output folder (now all should be integer-based)
for %%F in (LLY\Output\stand_*.las) do (
    set FNAME=stand_!COUNT!.las
    echo Normalizing %%F using ground.dtm...
    "c:\Users\W0491597\OneDrive - Nova Scotia Community College\AGRG\Fusion\ClipData.exe" %%F LLY\Output\normalized\!FNAME! /height /dtm:LLY\Output\ground.dtm
    IF !ERRORLEVEL! NEQ 0 (
        echo ClipData failed for %%F with error code !ERRORLEVEL!.
        exit /b !ERRORLEVEL!
    )
    set /a COUNT+=1
)

REM Optionally, you can add a renaming step before normalization to convert floating-point filenames to integer-based names if needed.

echo All stand files normalized to heights above ground. Output in LLY\Output\normalized
