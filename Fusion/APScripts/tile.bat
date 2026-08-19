REM Tile processing batch file for use with AreaProcessor

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

REM If doing bare ground filtering and surface creation, do it before any other tile processing.
REM Goal is to produce a ground surface model that will cover the buffered extent...needed to keep the edges of canopy models
REM and metrics cleaner. The *_TRIMMED.dtm surfaces are used to merge surfaces after all tile processing is complete.
IF /I [%DOGROUND%]==[true] (
	IF /I [%FILTERPOINTS%]==[true] (
		GroundFilter %CLASSOPTION% /extent:%BUFFEREDEXTENT% "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_pts.las" %FILTERCELLSIZE% %6
		GridSurfaceCreate /gridxy:%BUFFEREDEXTENT% "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_%GROUNDFILEIDENTIFIER%_BUFFERED.dtm" %GROUNDCELLSIZE% %COORDINFO% "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_pts.las"
	) ELSE (
		GridSurfaceCreate /class:2 /gridxy:%BUFFEREDEXTENT% "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_%GROUNDFILEIDENTIFIER%_BUFFERED.dtm" %GROUNDCELLSIZE% %COORDINFO% %6
	)
	ClipDtm "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_%GROUNDFILEIDENTIFIER%_BUFFERED.dtm" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%1_BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm" %2 %3 %4 %5
)

REM set the command line options for CanopyModel
SET CM_OPTIONS=/gridxy:%BUFFEREDEXTENT% "/ground:%DTMSPEC%" /outlier:%OUTLIER% %CLASSOPTION%

REM do canopy surfaces and GridSurfaceStats to compute canopy metrics
IF /I [%DOCANOPY%]==[true] (
	CanopyModel %CM_OPTIONS% "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm" %CANOPYCELLSIZE% %COORDINFO% %6
	CanopyModel /smooth:3 %CM_OPTIONS% "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" %CANOPYCELLSIZE% %COORDINFO% %6

	REM compute grid surface stats and clip these to the unbuffered tile extent
	gridsurfacestats /halfcell "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%" %CANOPYSTATSCELLMULTIPLIER%
	clipdtm "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_surface_area_ratio.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_rumple_%CANOPYSTATSFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	clipdtm "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_surface_volume_ratio.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_FPV_%CANOPYSTATSFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	clipdtm "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_stddev_height.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_sd_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	clipdtm "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_mean_height.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_average_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	clipdtm "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_max_height.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_maximum_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" %2 %3 %4 %5

	REM clip canopy surface models back by 1 analysis cell to remove problems around the edges related to smoothing
	REM rename the target CSM to a temp name, clip the temp file and name the output using the original target CSM, delete the temp file
	REN "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "CSM_temp.dtm"
	clipdtm "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CSM_temp.dtm" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	DEL "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CSM_temp.dtm"

	REN "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "CSM_temp.dtm"
	clipdtm "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CSM_temp.dtm" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%1_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" %2 %3 %4 %5
	DEL "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CSM_temp.dtm"

	REM delete the grid surface stat outputs that have a buffer around them
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_surface_area_ratio.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_surface_volume_ratio.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_stddev_height.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_mean_height.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_max_height.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_surface_volume.dtm"
	DEL "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_%CANOPYSTATSFILEIDENTIFIER%_potential_volume.dtm"
)

REM enable delayed expansion for environment variables...this lets us redefine the same variable in a loop or if stmt since the loop or if stmt is read as 
REM a single command by the command interpreter
SETLOCAL ENABLEDELAYEDEXPANSION

REM set the command line options for GridMetrics
SET GM_OPTIONS=/verbose /minht:%HTCUTOFF% /buffer:%7 /outlier:%OUTLIER% %CLASSOPTION%

SET GM_OPTIONS=%GM_OPTIONS% /gridxy:%2,%3,%4,%5 

IF /I [%OMITINTENSITY%]==[true] SET GM_OPTIONS=%GM_OPTIONS% /nointensity
IF /I [%DOSTRATA%]==[true] SET GM_OPTIONS=%GM_OPTIONS% /strata:%STRATAHEIGHTS%
IF /I [%DOTOPO%]==[true] SET GM_OPTIONS=%GM_OPTIONS% /topo:%TOPOCELLSIZE%,%LATITUDE%

IF /I [%DOMETRICS%]==[true] (
	gridmetrics %GM_OPTIONS% "%DTMSPEC%" %COVERCUTOFF% %CELLSIZE% "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_metrics.csv" %6

	IF /I [%DOFIRSTMETRICS%]==[true] (
		REM get intensity metrics for first returns...ignore strata, topo, omitintensity	
		SET GM_OPTIONS=/verbose /first /minht:%HTCUTOFF% /buffer:%7 /outlier:%OUTLIER% %CLASSOPTION%

		SET GM_OPTIONS=!GM_OPTIONS! /gridxy:%2,%3,%4,%5 

		IF /I [%DOFIRSTSTRATA%]==[true] SET GM_OPTIONS=!GM_OPTIONS! /strata:%STRATAHEIGHTS%
		gridmetrics !GM_OPTIONS! "%DTMSPEC%" %COVERCUTOFF% %CELLSIZE% "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\%1_metrics.csv" %6
	)
)

ENDLOCAL
