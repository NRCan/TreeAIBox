REM merge all files with the name passed on the command line across all blocks of a job
REM 3/5/2018 Changed so DTM files are converted to IMG format after the merge
REM
REM %1 -- full file name (name + extension) for files to merge without drive or path
REM %2 -- format code (blank or 1 = ASCII raster, 2 = DTM, 3 = BMP...not currently supported)
REM %3 -- folder for merged output...assume folder exists

REM build list of input files
DIR /b /s "%PRODUCTHOME%\..\%~1" > layerfiles.txt

REM do the merge...the ~ removes quotation marks from the variable
IF "%2"=="1" (
	REM ASCII raster format
	mergeraster /overlap:max "%~3\%~1" layerfiles.txt
) ELSE (
	IF "%2"=="2" (
		REM DTM format
		mergedtm /overlap:max "%~3\%~1" layerfiles.txt
	) ELSE (
		REM image format
	)
)

REM we don't know how to merge images so jump to end
IF "%2"=="3" GOTO END

REM copy base projection info
IF NOT "%BASEPRJ%"=="" (
   COPY "%BASEPRJ%" "%~3\%~n1.prj"
)

REM convert to imagine format...convert2img check to see if it supposed to do the conversion (checks CONVERTTOIMG)
IF "%2"=="1" (
	CALL "%PROCESSINGHOME%\convert2img" "%~3\%~1" "%~3"
) ELSE (
	IF "%2"=="2" (
		REM DTM format...need to convert to ASCII raster format then to IMG
		REM if CONVERTTOIMG is FALSE, you will end up with ASCII files but no IMG files...this may be good
		REM if you don't want the DTM->ASCII conversion to take place, test for CONVERTTOIMG and only run DTM2ASCII if it is TRUE
		DTM2ASCII "%~3\%~1" "%~3\%~n1.asc"

		CALL "%PROCESSINGHOME%\convert2img" "%~3\%~n1.asc" "%~3"
	)
)

:END

REM delete temporary list of layer files
DEL layerfiles.txt
