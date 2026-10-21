REM move a file then rename it
REM this was originally written because I didn't know about the /Y option and the ability to use MOVE to move a single file and rename it with a single command
REM %1 in original folder...no trailing \
REM %2 is the original file name
REM %3 is the new folder...no trailing \
REM %4 is the new file name

REM ~ removes quotation marks from string
REM move the original file to the new folder, /Y allow us to overwrite an exiting file in the new folder
MOVE /Y "%~1\%~2" "%~3\%~4"
