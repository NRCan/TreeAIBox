REM extract metrics from CSV files and merge into a single coverage
REM batch runs from processing folder for each area
REM %FILEIDENTIFIER% is the cell size identifier added to each file name
REM %CANOPYFILEIDENTIFIER% is the cell size identifier added to each file name for canopy surface models
REM %GROUNDFILEIDENTIFIER% is the cell size identifier added to each file name for ground surface models

REM build the strings used to label layers
SET MINHTLABEL=%HTCUTOFF:.=p%
SET COVERHTLABEL=%COVERCUTOFF:.=p%

REM merge bare ground surfaces and convert to ASCII raster
REM The _BUFFERED surface tiles will probably have edge artifacts when merged. However, they are great for computing tile metrics.
IF /I [%DOGROUND%]==[true] (
	mergedtm "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\*BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm"

	dtm2ascii "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm"
	REM COPY base projection info
	IF NOT "%BASEPRJ%"=="" (
		COPY "%BASEPRJ%" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\BE_%GROUNDFILEIDENTIFIER%_TRIMMED.prj"
	)

	REM If we are not merging final outputs and we are working on a block, move the outputs. Can't move and rename in one command so we move first then rename the file
	IF /I NOT "%MERGEBLOCKGROUND%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm" "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "%BLOCKNAME%_BE_%GROUNDFILEIDENTIFIER%_TRIMMED.dtm"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "BE_%GROUNDFILEIDENTIFIER%_TRIMMED.asc" "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "%BLOCKNAME%_BE_%GROUNDFILEIDENTIFIER%_TRIMMED.asc"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "BE_%GROUNDFILEIDENTIFIER%_TRIMMED.prj" "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%" "%BLOCKNAME%_BE_%GROUNDFILEIDENTIFIER%_TRIMMED.prj"

			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\%BLOCKNAME%_BE_%GROUNDFILEIDENTIFIER%_TRIMMED.asc" "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%"
		)
	)
)

REM Deal with canopy surfaces and stats
IF /I [%DOCANOPY%]==[true] (
	REM merge canopy surface stats
	mergedtm /nofill "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_rumple_%CANOPYSTATSFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\*_rumple_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	mergedtm /nofill "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_FPV_%CANOPYSTATSFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\*_FPV_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	mergedtm /nofill "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_stddev_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\*_sd_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	mergedtm /nofill "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_average_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\*_average_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	mergedtm /nofill "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_maximum_height_%CANOPYSTATSFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%\*_maximum_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"

	REM convert to ASCII raster format...need /raster option
	dtm2ascii /raster "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_rumple_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	dtm2ascii /raster "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_FPV_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	dtm2ascii /multiplier:%MULTIPLIER% /raster "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_stddev_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	dtm2ascii /multiplier:%MULTIPLIER% /raster "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_average_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"
	dtm2ascii /multiplier:%MULTIPLIER% /raster "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_maximum_height_%CANOPYSTATSFILEIDENTIFIER%.dtm"

	REM merge canopy height models
	mergedtm /nofill "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\*filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm"
	mergedtm /nofill "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\*filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm"

	REM convert to ASCII raster format...don't need raster option
	dtm2ascii /multiplier:%MULTIPLIER% "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm"
	dtm2ascii /multiplier:%MULTIPLIER% "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm"

	REM COPY base projection info
	IF NOT "%BASEPRJ%"=="" (
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_rumple_%CANOPYSTATSFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_FPV_%CANOPYSTATSFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_stddev_height_%CANOPYSTATSFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_average_height_%CANOPYSTATSFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%\canopy_maximum_height_%CANOPYSTATSFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.prj"
		COPY "%BASEPRJ%" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.prj"
	)

	REM IF we are not merging final canopy surfaces and we are working on a block, move the outputs
	IF /I NOT "%MERGEBLOCKCANOPY%"=="true" (
		IF NOT "%BLOCKNAME%"=="" (
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.dtm"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.asc" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.asc"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.prj" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%BLOCKNAME%_CHM_filled_3x_smoothed_%CANOPYFILEIDENTIFIER%.asc" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%"

			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.dtm"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.asc" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.asc"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.prj" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%" "%BLOCKNAME%_CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.prj"
			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%\%BLOCKNAME%_CHM_filled_not_smoothed_%CANOPYFILEIDENTIFIER%.asc" "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%"
		)
	)
)

REM intensity images...does not use the buffered extent
IF /I [%DOINTENSITY%]==[true] (
	IF /I [%DODENSITY%]==[true] (
		catalog %CLASSOPTION% /rawcounts /density:%INTENSITYCELLAREA%,4,20 /bmp /noclasssummary /intensity:%INTENSITYCELLAREA%,%INTENSITYRANGE% /imageextent:%BLOCKEXTENT% "%AP_INPUTTILES%" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\temp.csv"
	) ELSE (
		catalog %CLASSOPTION% /bmp /noclasssummary /intensity:%INTENSITYCELLAREA%,%INTENSITYRANGE% /imageextent:%BLOCKEXTENT% "%AP_INPUTTILES%" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\temp.csv"
	)

	REM deal with the intensity image from Catalog
	IF NOT "%BASEPRJ%"=="" (
		COPY "%BASEPRJ%" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\temp_intensity.prj"
	)

	IF NOT "%BLOCKNAME%"=="" (
		REM rename intensity image and world file using block name
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.bmp" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp"
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.bmpw" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.prj" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.prj"

		REM IF we are not merging final images and we are working on a block, move the outputs
		IF /I NOT "%MERGEBLOCKINTENSITY%"=="true" (
			REM move files to final products folder
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp" "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw" "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
			CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.prj" "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.prj"

			CALL "%PROCESSINGHOME%\convert2img" "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp" "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%"

			REM delete world file
			IF /I NOT "%KEEPASCIIFILES%"=="true" (
				DEL "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
			)
		) ELSE (
			CALL "%PROCESSINGHOME%\convert2img" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%"

			REM delete world file
			IF /I NOT "%KEEPASCIIFILES%"=="true" (
				DEL "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\%BLOCKNAME%_Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
			)
		)
	) ELSE (
		REM rename intensity image and world file
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.bmp" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp"
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.bmpw" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
		CALL "%PROCESSINGHOME%\move_rename" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "temp_intensity.prj" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%" "Intensity_Mean_%INTENSITYFILEIDENTIFIER%.prj"

		CALL "%PROCESSINGHOME%\convert2img" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmp" "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%"

		REM delete world file
		IF /I NOT "%KEEPASCIIFILES%"=="true" (
			DEL "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\Intensity_Mean_%INTENSITYFILEIDENTIFIER%.bmpw"
		)
	)

	REM delete other files produced by Catalog
	DEL "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\temp*.*"
	DEL "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%\temp.*"
)

REM extract elevation metrics to layers
IF /I [%DOMETRICS%]==[true] (
	CALL %PROCESSINGHOME%\buildlayers_allreturns.bat
	IF /I [%DOFIRSTMETRICS%]==[true] (
		CALL %PROCESSINGHOME%\buildlayers_firstreturns.bat
	)

	REM extract topo metrics to layers
	IF /I [%DOTOPO%]==[true] (
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 5 topo_elevation_%FILEIDENTIFIER% %MULTIPLIER%
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 6 topo_slope_%FILEIDENTIFIER% 1
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 7 topo_aspect_%FILEIDENTIFIER% 1
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 8 topo_profilecurv_%FILEIDENTIFIER% 1
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 9 topo_plancurv_%FILEIDENTIFIER% 1
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 10 topo_sri_%FILEIDENTIFIER% 1
		CALL "%PROCESSINGHOME%\extract_metric" _topo_metrics 11 topo_curvature_%FILEIDENTIFIER% 1
	)

	IF /I [%DOSTRATA%]==[true] (
		CALL "%PROCESSINGHOME%\buildstrata"
	)
)

:end

REM clear label variables
SET MINHTLABEL=
SET COVERHTLABEL=
