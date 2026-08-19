REM Tile processing batch file for use with AreaProcessor
REM This script ONLY computes return density for the point tile

REM Expected command line parameters:
REM    %1     Name of the buffered tile containing LIDAR data
REM    %2     Minimum X value for the unbuffered tile
REM    %3     Minimum Y value for the unbuffered tile
REM    %4     Maximum X value for the unbuffered tile
REM    %5     Maximum Y value for the unbuffered tile
REM    %6     Minimum X value for the buffered tile
REM    %7     Minimum Y value for the buffered tile
REM    %8     Maximum X value for the buffered tile
REM    %9     Maximum Y value for the buffered tile
REM The buffered tile file name looks like this: TILE_C00001_R00002_S00001. The row (R) and column (C) numbers
REM specify the tile location and the subtile designation identifies the tile within an analysis grid cell when
REM tile sizes have been optimized. The origin of the row and column coordinate system is the lower left corner
REM of the data extent.

REM Initially, the values for %2, %3, %4, %5 can be used to clip data products produced using the buffered tile

REM Insert commands that use the original tile corners before the the block of SHIFT commands

REM save the variables for the buffered tile corners so we can use them after the SHIFT
SET BUFFER_MINX=%6
SET BUFFER_MINY=%7
SET BUFFER_MAXX=%8
SET BUFFER_MAXY=%9

SET BUFFEREDEXTENT=%6,%7,%8,%9

REM ------------------------------------------------------
REM After the 4 SHIFT commands, variables %6, %7, %8, %9 contain the following values:

REM    %6     Name of the text file containing a list of all data files
REM    %7     Buffer size
REM    %8     Width of the unbuffered analysis tile
REM    %9     Height of the unbuffered analysis tile

REM SHIFT command moves command line parameters one position. For example, %10 moves to %9.
REM This is necessary because DOS cannot directly reference more than 9 command line parameters
REM since %10 would be interpreted as %1.

REM Shift last four variables (%10-%14) into positions %6-%9
SHIFT /6
SHIFT /6
SHIFT /6
SHIFT /6

REM Insert commands that use the buffer width and all data files after the block of SHIFT commands

rem enable delayed expansion for environment variables...this lets us redefine the same variable in a loop or if stmt since the loop or if stmt is read as 
rem a single command by the command interpreter
SETLOCAL ENABLEDELAYEDEXPANSION

REM set the command line options for ReturnDensity
SET RD_OPTIONS=/verbose %CLASSOPTION% /gridxy:%2,%3,%4,%5
IF /I "%CONVERTTOIMG%"=="true" (
	SET RD_OPTIONS=%RD_OPTIONS% "/projection:%BASEPRJ%" /ascii
)

returndensity %RD_OPTIONS% "%FINALPRODUCTHOME%\Metrics_%FILEIDENTIFIER%\%1_returndensity.dtm" %CELLSIZE% %6

IF /I "%CONVERTTOIMG%"=="true" (
	CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\Metrics_%FILEIDENTIFIER%\%1_returndensity.asc" "%FINALPRODUCTHOME%\Metrics_%FILEIDENTIFIER%"
)

ENDLOCAL
