@echo off
setlocal EnableDelayedExpansion
set FUSION64=TRUE
REM Loop through each stand file in stand_filelist.txt
for /F "tokens=*" %%F in (LLY\Output\stand_filelist.txt) do (
    call process_single_stand_grid.bat "LLY\Output\%%F"
)
echo All stand grid metrics processing complete.
endlocal
