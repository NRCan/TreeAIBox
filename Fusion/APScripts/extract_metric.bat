@ECHO OFF
REM extract a specific metric from CSV files produced by Gridmetrics

IF "%1"=="" GOTO syntax
IF "%2"=="" GOTO syntax
IF "%3"=="" GOTO syntax
IF "%4"=="" GOTO syntax
GOTO process

:syntax
ECHO extractmetric fileidentifier column name multiplier [outputflag]
ECHO fileidentifier designates which CSV output file is used FOR the metrics
ECHO column is the column number in the GridMetrics CSV output
ECHO name is the name used FOR the merged output ASCII raster file (don't include the .asc extension)
ECHO multiplier used FOR each cell value (normally 1.0)
ECHO (optional) outputflag is used to direct outputs to specific folders. Use for TOPO, FINETOPO, and STRATA outputs

GOTO end

:process
@ECHO ON

REM set up output folder
SET OUTPUTFOLDER=Metrics_%FILEIDENTIFIER%
IF /I "%5"=="TOPO" SET OUTPUTFOLDER=TopoMetrics_%TOPOFILEIDENTIFIER%
IF /I "%5"=="FINETOPO" SET OUTPUTFOLDER=FineTopoMetrics_%FINETOPOFILEIDENTIFIER%
IF /I "%5"=="STRATA" SET OUTPUTFOLDER=StrataMetrics_%FILEIDENTIFIER%

REM do the extraction from each tile
CD "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%"

DIR /b *%1.csv > csvlist.txt

REM loop through all CSV files in folder and do processing
FOR /F "eol=; tokens=1* delims=,. " %%i IN (csvlist.txt) DO CALL "%PROCESSINGHOME%\doextractmetric" %%i %2 %4

REM merge tiles...ASCII raster format
mergeraster /verbose /compare /overlap:new %3.asc *_tile.asc

REM delete ASCII raster tiles
DEL *_tile.asc

REM move layer to Metrics folder
MOVE /Y %3.asc "%PRODUCTHOME%\%OUTPUTFOLDER%"

REM copy base projection info
IF NOT "%BASEPRJ%"=="" (
	COPY "%BASEPRJ%" "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.prj"
)

REM IF we are not merging final outputs and we are working on a block, move the outputs
IF /I "%5"=="" (
	IF /I NOT "%MERGEBLOCKMETRICS%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc"
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.prj" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%"
		)
	)
)

IF /I "%5"=="STRATA" (
	IF /I NOT "%MERGEBLOCKMETRICS%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc"
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.prj" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%"
		)
	)
)

IF /I "%5"=="TOPO" (
	IF /I NOT "%MERGEBLOCKTOPOMETRICS%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc"
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.prj" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%"
		)
	)
)
IF /I "%5"=="FINETOPO" (
	IF /I NOT "%MERGEBLOCKFINETOPOMETRICS%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc"
			MOVE "%PRODUCTHOME%\%OUTPUTFOLDER%\%3.prj" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%\%BLOCKNAME%_%3.asc" "%FINALPRODUCTHOME%\%OUTPUTFOLDER%"
		)
	)
)

REM delete list file
DEL csvlist.txt

CD "%PROCESSINGHOME%"

:end

@ECHO ON
