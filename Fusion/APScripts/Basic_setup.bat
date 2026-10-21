REM **************************************************************************************************************
REM *****             setup batch file used in conjunction with FUSION's AreaProcessor tool                  *****
REM *****                                                                                                    *****
REM *****     Used to set up folder structure for data and variables to control run for producing output     *****
REM *****                                 from point and surface data                                        *****
REM **************************************************************************************************************

REM ###########################################################
REM           Overall options to compute metrics
REM ###########################################################

REM DOMETRICS controls whether gridmetrics is run using all returns
REM DOFIRSTMETRICS controls whether gridmetrics is separately run to calculate metrics using only first returns
REM DOSTRATA controls whether gridmetrics using all returns produces metrics for strata breaks at 0.5,1,2,4,8,16,32,48,64 m
REM DOCANOPY controls whether canopy surface models are created and whether gridsurfacestats is run
REM DOGROUND controls whether a ground model is created; if not, the vendor's ground model is used
REM DOINTENSITY controls whether intensity images ae created

REM if DOCANOPY is FALSE and CANOPYALIGNTORUMPLE is TRUE, things will not process correctly and you will have lots of errors.

SET DOMETRICS=TRUE
SET DOFIRSTMETRICS=TRUE
SET DOSTRATA=TRUE
SET DOCANOPY=TRUE
SET DOGROUND=FALSE
SET DOINTENSITY=TRUE
SET DOTOPO=TRUE

REM compute strata metrics using only first returns
SET DOFIRSTSTRATA=FALSE

REM flag to control conversion of all outputs to IMAGINE format. the default format is ASCII raster. IMAGINE format is much more compact
REM and the files contain embedded projection information. projection info for ASCII raster files is help in a separate .PRJ file.
SET CONVERTTOIMG=TRUE

REM flag to delete intermediate ASCII raster files and intermediate BMP files (intensity images). You can set this to TRUE to keep the "fluffy" files
REM but they use up quite a bit of disk space.
SET KEEPASCIIFILES=FALSE

REM flag to omit intensity metrics when running GridMetrics. This really doesn't save much time so we leave it FALSE
SET OMITINTENSITY=FALSE

REM FILTERPOINTS controls the behavior used to identify bare-ground points. If TRUE and DOGROUND is TRUE, GroundFilter is used to 
REM identify bare-ground points from the full point cloud and the resulting point files are used to create the gridded ground models.
REM If FALSE and DOGROUND is TRUE, points classified as bare ground (class 2) in LAS files are used to build ground surfaces.
SET FILTERPOINTS=FALSE

REM Set variables to control merging of block outputs after all processing is complete. The final merge only occurs for jobs processed using blocks.
REM In general, we merge 30m metrics and other products using larger cells and do not merge any of the high-resolution outputs. If the area is small,
REM you can probably merge the high-resolution products.
SET MERGEBLOCKMETRICS=TRUE
SET MERGEBLOCKCANOPY=TRUE
SET MERGEBLOCKGROUND=FALSE
SET MERGEBLOCKTOPOMETRICS=TRUE

REM we currently have no way to merge image outputs so MERGEBLOCKINTENSITY should always be FALSE
SET MERGEBLOCKINTENSITY=FALSE

REM ###########################################################
REM           Pick up variables from AreaProcessor
REM ###########################################################

REM Set the overall name for the area. This will be incorporated into output folder names
REM pick up the value from the area-specific parameters in AreaProcessor, otherwise use a default
IF "%AP_AREANAME%"=="" (
   SET AREA=MyArea
) ELSE (
   SET AREA=%AP_AREANAME%
)

REM coordinate system 0=state plane, 1=UTM, 2=other
REM coordinate system info is not used for much...if using something other than state plane or UTM, SET COORDSYSTEM=2 and COORDZONE=0
REM if you try to merge data with different coordinate systems, the merge tools will report the difference and fail gracefully.
IF "%AP_COORDSYSTEM%"=="" (
   SET COORDSYSTEM=1
) ELSE (
   SET COORDSYSTEM=%AP_COORDSYSTEM%
)
IF "%AP_COORDZONE%"=="" (
   SET COORDZONE=10
) ELSE (
   SET COORDZONE=%AP_COORDZONE%
)

REM Set the latitude for the approximate center of the project area. This is only used for solar radiation index calculations.
IF "%AP_LATITUDE%"=="" (
   SET LATITUDE=40.00
) ELSE (
   SET LATITUDE=%AP_LATITUDE%
)

REM Set UNITS for the project...can be FEET or METERS
REM these are the units for the input data; output will be in METERS
IF "%AP_UNITS%"=="" (
   SET UNITS=METERS
) ELSE (
   SET UNITS=%AP_UNITS%
)

REM range for Catalog call to create intensity images...must be min,max with no extra spaces
REM You will need to examine some LAS files to figure out this range. Intensity can be 8 bit (values from 0-255) or 16-bit (values from 0-64,536)
REM Use a range from -1 to the maximum value-1. this will prevent any pixels in the image from having a value of 0 when the cell contains data. The background of
REM the image is SET to RGB(0,0,0) so you can identify all areas with a value of 0 in the grayscale image as NODATA.
REM Many data sets don't use the full range of values so youi really need to look at some data to figure out a good range. You can do this in FUSION using the 
REM Tools...Miscellaneous utilities...Create an image using LIDAR point data menu option or by experimenting with the sample options using "Color by intensity"
REM and examining the range of values in samples.
rem
IF "%AP_INTENSITYRANGE%"=="" (
   SET INTENSITYRANGE=-1,254
) ELSE (
   SET INTENSITYRANGE=%AP_INTENSITYRANGE%
)

REM CLASSOPTION is used to include/exclude points with specific LAS classification values
REM The option should include the leading "/" character
REM The CLASSOPTION is added to calls to GroundFilter, CanopyModel, Catalog (for intensity images) and GridMetrics in tile.bat
REM Class 7 points are low noise, class 9 is water. NCALM has been known to SET noise points to class 9
IF "%AP_CLASSOPTION%"=="" (
   SET CLASSOPTION=/class:~7,9
) ELSE (
   SET CLASSOPTION=%AP_CLASSOPTION%
)

REM directory where the user-supplied auxiliary processing scripts are stored...this can be anywhere but we try to use the same SET of
REM scripts for all runs. All of the files in the specified folder will be copied to the FINAL products folder so you should always try
REM to keep all of the auxiliary scripts in the same folder. Auxiliary scripts are those that are called from the scripts specified in 
REM AreaProcesor's "Processing scripts" dialog.
REM If this folder is specified in AreaProcessor, it will be used through all the scripts. If a folder is not specified in AreaProcessor
REM the folder must be explicitly specified in the setup batch file.
rem
REM Use the folder specified in AreaProcessor. This folder should stay the same for all runs unless you have a good reason to change it.
REM original location just in case someone changes things: C:\FUSION\AP_ProcessingScripts
IF "%AP_PROCESSINGHOME%"=="" (
   SET PROCESSINGHOME=C:\FUSION\AP_ProcessingScripts
) ELSE (
   SET PROCESSINGHOME=%AP_PROCESSINGHOME%
)

REM Set the file used to associate projection info with all output layers...this file is associated with all ASCII raster file outputs.
REM The projection file is a .PRJ file that will be copied for each layer of metrics. This is not a required file but it makes the output layers
REM much easier to work with in GIS. In AreaProcessor, you can optionally specify the projection file. If this is done, the AP_PROJECTIONFILE
REM will contain the file name. Otherwise, AP_PROJECTIONFILE will not be defined so you must specify your own projection file name.
REM Make sure the projection file is the correct format (all data on 1 line) or else the conversion from ASCII raster to ither formats
REM will not have projection info (gdal_translate doesn't recognize multi-line projection files)
IF "%AP_PROJECTIONFILE%"=="" (
   SET BASEPRJ=%PROCESSINGHOME%\utm10.prj
) ELSE (
   SET BASEPRJ=%AP_PROJECTIONFILE%
)

REM The AP_ALIGNMENT_CELLSIZE variable is also available from AreaProcessor. However, you need to be very careful if you change the cellsize
REM for the metrics as there are several other variables that are affected when the cell size is changed. Ideally, the setup script would
REM make the necessary changes to all variables but you can't do floating point math easily within a batch file so it is hard to compute
REM the new values.

REM ###########################################################
REM           GDAL installation information
REM ###########################################################
REM location where gdal_translate is installed...full path with drive letter...DO NOT enclose the path in quotation marks
REM look for a separate configuration file and use it if found, otherwise set the "standard" GDAl install location
IF EXIST "%PROCESSINGHOME%\ComputerSpecific\GDALconfig.bat" (
   CALL %PROCESSINGHOME%\ComputerSpecific\GDALconfig.bat
) ELSE (
   SET GDAL_TRANSLATE_LOCATION=C:\Program Files\GDAL\gdal_translate
   SET GDAL_DATA=C:\Program Files\GDAL\gdal-data
)

REM ###########################################################
REM           Parameters for ground filtering
REM ###########################################################
REM Set variables for ground point filtering and surface creation
REM The GROUNDCELLSIZE is the cell size for the final ground models. FILTERCELLSIZE controls the ground point filtering process
REM and relates to the largest area without actual ground points that will be spanned by intermediate surface models during 
REM filtering.
IF /I [%UNITS%]==[feet] (
	SET GROUNDCELLSIZE=5
	SET FILTERCELLSIZE=20
) ELSE (
	SET GROUNDCELLSIZE=1
	SET FILTERCELLSIZE=6
)

REM ###########################################################
REM           Parameters for general processing
REM ###########################################################
REM Set variables to establish grid cell size, height cutoffs, coordinate system info for grids, and outlier limits
REM Set up for topo metrics using multiple window sizes...also uses the TOPOCELLSIZE and LATITUDE variables
REM I have used the conversion factor of 3.2808 ft/m. You can use something more precise but you must make sure that
REM all sizes are multiples of the basic cell size. Failure to do this will cause problems when products are merged.
REM The window sizes for topographic metrics do not need to be a multiple of the basic cell size but the output cell
REM size for topographic metrics should be the same as the basic cell size. For fine topographic metrics, the cell size
EM should divide evenly into the basic cell size.
IF /I [%UNITS%]==[feet] (
	SET CELLSIZE=98.424
	SET HTCUTOFF=6.5616
	SET COVERCUTOFF=6.5616
	SET COORDINFO=f f %COORDSYSTEM% %COORDZONE% 2 2
	SET OUTLIER=-98.424,492.12
	SET MULTIPLIER=0.3048
	SET TOPOCELLSIZE=98.424
	SET INTENSITYCELLSIZE=4.9212
	SET INTENSITYCELLAREA=24.2182
	SET MULTITOPOWINDOWSIZES=49.212,147.636,442.908,885.816
	SET MULTITPIWINDOWSIZES=656.16,1640.40,3280.80,6561.60,13123.2
	SET FINETOPOCELLSIZE=3.2808
	SET FINEMULTITOPOWINDOWSIZES=16.404,32.808,49.212,98.424,196.848
	SET FINEMULTITPIWINDOWSIZES=32.808,65.616,98.424,196.848,393.696
) ELSE (
	SET CELLSIZE=30
	SET HTCUTOFF=2
	SET COVERCUTOFF=2
	SET COORDINFO=m m %COORDSYSTEM% %COORDZONE% 2 2
	SET OUTLIER=-30,150
	SET MULTIPLIER=1
	SET TOPOCELLSIZE=30
	SET INTENSITYCELLSIZE=1.5
	SET INTENSITYCELLAREA=2.25
 	SET MULTITOPOWINDOWSIZES=15,45,135,270
	SET MULTITPIWINDOWSIZES=200,500,1000,2000,4000
	SET FINETOPOCELLSIZE=1
	SET FINEMULTITOPOWINDOWSIZES=5,10,15,30,60
	SET FINEMULTITPIWINDOWSIZES=10,20,30,60,120
)

REM Set variables for strata calculation and output
REM STRATALAYERS is no longer needed...number of layers is figured out from the list of height breaks
IF /I [%UNITS%]==[feet] (
	SET STRATAHEIGHTS=1.6404,3.2808,6.5616,13.1232,26.2464,52.4928,104.9856,157.4784,209.9712
) ELSE (
	SET STRATAHEIGHTS=0.5,1,2,4,8,16,32,48,64
)

REM Set variables for canopy height models and GridSurfaceStats. CANOPYCELLSIZE * CANOPYSTATSCELLMULTIPLIER must equal the basic cell size
IF /I [%UNITS%]==[feet] (
	SET CANOPYCELLSIZE=3.2808
	SET CANOPYSTATSCELLMULTIPLIER=30
) ELSE (
	SET CANOPYCELLSIZE=1.0
	SET CANOPYSTATSCELLMULTIPLIER=30
)

REM ###########################################################
REM           Labels for output folders and files
REM ###########################################################
REM Set the idenstifier for ground surface models
SET GROUNDFILEIDENTIFIER=%GROUNDCELLSIZE:.=p%%UNITS%

REM Set file identifiers for topo metrics
SET TOPOFILEIDENTIFIER=%TOPOCELLSIZE:.=p%%UNITS%

REM Set file identifier for intensity images
SET INTENSITYFILEIDENTIFIER=%INTENSITYCELLSIZE:.=p%%UNITS%

REM Set file identifier for intensity images
SET CANOPYFILEIDENTIFIER=%CANOPYCELLSIZE:.=p%%UNITS%

REM Build identifiers for canopy metrics...This assumes that the canopy metrics use the same cell size as the basic cell size. If this is not the
REM case, you must must set the identifier for the canopy stats explicitly since we can't do floating point math using the SET /A command.
REM The size would be CANOPYCELLSIZE * CANOPYSTATSCELLMULTIPLIER if we could do the math.
SET CANOPYSTATSFILEIDENTIFIER=%CELLSIZE:.=p%%UNITS%

REM IF /I [%UNITS%]==[feet] (
REM	SET CANOPYSTATSFILEIDENTIFIER=98p424%UNITS%
REM ) ELSE (
REM	SET CANOPYSTATSFILEIDENTIFIER=30%UNITS%
REM)

REM build cell size identifier...used for folders and filenames
SET FILEIDENTIFIER=%CELLSIZE:.=p%%UNITS%

REM ###########################################################
REM           Set up folder names for outputs
REM ###########################################################
REM directory where outputs will be stored...WORKINGDIRECTORY is defined in the master script for the job
REM The output folder is named using the AREA name and the RUNDATE
IF "%BLOCKNAME%"=="" (
   SET PRODUCTHOME=%WORKINGDIRNAME%\Products_%AREA%_%AP_RUNDATE%
   SET FINALPRODUCTHOME=%WORKINGDIRNAME%\Products_%AREA%_%AP_RUNDATE%
) ELSE (
   SET PRODUCTHOME=%WORKINGDIRNAME%\Products_%AREA%_%AP_RUNDATE%\%BLOCKNAME%

   REM create the directory name for the merged layers
   SET FINALPRODUCTHOME=%WORKINGDIRNAME%\Products_%AREA%_%AP_RUNDATE%\FINAL_%AREA%_%AP_RUNDATE%
)

REM file specifier for bare-ground .DTM files...can be path and name of text file with list of .DTM files, a single file name, or a file
REM specifier that uses wild card characters.
REM AP_BAREGROUND is defined in the scripts generated by the AreaProcessor tool if the user specifies bare-ground files.
REM If you are building ground files on-the-fly (DOGROUND is TRUE), we need to SET the specifier to point to the files created by
REM GridSurfaceCreate or any other tool used to produce the gridded surface files.
IF /I [%DOGROUND%]==[true] (
	SET DTMSPEC=%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%\*_BUFFERED.dtm
) ELSE (
	SET DTMSPEC=%AP_BAREGROUND%
)

REM Set up a file to record output folders for all blocks. As blocks are processed, the output folder will be added to the file.
REM The post-block processing script will use this list to build a list of outputs for the blocks. We expect this file to only get
REM some of the block output folders for multi-process jobs since different processes will try to write to the file at the same time.
REM This is OK as we only need the name of one output folder (block) to build the list of outputs for the final merges.
ECHO %PRODUCTHOME%>>"%WORKINGDIRNAME%\OutputFolders.txt"

REM ###########################################################
REM           Create directory structure for outputs
REM ###########################################################
CD "%WORKINGDIRNAME%"
MKDIR "%PRODUCTHOME%"
MKDIR "%PRODUCTHOME%\TileMetrics_%FILEIDENTIFIER%"
IF /I "%DOGROUND%"=="true" MKDIR "%PRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%"
IF /I "%DOCANOPY%"=="true" MKDIR "%PRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%"
IF /I "%DOCANOPY%"=="true" MKDIR "%PRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%"
IF /I "%DOMETRICS%"=="true" (
	MKDIR "%PRODUCTHOME%\Metrics_%FILEIDENTIFIER%"
)
IF /I "%DOINTENSITY%"=="true" (
	MKDIR "%PRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%"
)	
IF /I "%DOSTRATA%"=="true" MKDIR "%PRODUCTHOME%\StrataMetrics_%FILEIDENTIFIER%

REM MKDIR "%PRODUCTHOME%\QAQC"

REM create directory structure for final outputs
REM we always need the home folder because we copy the batch files into a subfolder
MKDIR "%FINALPRODUCTHOME%"
IF NOT "%BLOCKNAME%"=="" (
   REM create directory structure for merged outputs
   IF /I "%DOGROUND%"=="true" MKDIR "%FINALPRODUCTHOME%\BareGround_%GROUNDFILEIDENTIFIER%"
   IF /I "%DOCANOPY%"=="true" MKDIR "%FINALPRODUCTHOME%\CanopyHeight_%CANOPYFILEIDENTIFIER%"
   IF /I "%DOCANOPY%"=="true" MKDIR "%FINALPRODUCTHOME%\CanopyMetrics_%CANOPYSTATSFILEIDENTIFIER%"
   IF /I "%DOMETRICS%"=="true" MKDIR "%FINALPRODUCTHOME%\Metrics_%FILEIDENTIFIER%"
   IF /I "%DOINTENSITY%"=="true" MKDIR "%FINALPRODUCTHOME%\Intensity_%INTENSITYFILEIDENTIFIER%"
   IF /I "%DOSTRATA%"=="true" MKDIR "%FINALPRODUCTHOME%\StrataMetrics_%FILEIDENTIFIER%
)

REM ###########################################################
REM           Copy the batch files used for processing
REM ###########################################################
REM copy the setup batch file...%0 is the full path to the currently running file...this means that the setup batch file can be in a different folder
REM than all the other batch files
REM also copy the original projection file to the scripts folder
IF NOT EXIST "%FINALPRODUCTHOME%\Scripts" (
	MKDIR "%FINALPRODUCTHOME%\Scripts"
	ECHO %PROCESSINGHOME%>%FINALPRODUCTHOME%\Scripts\AccessoryScriptFolder.txt
	COPY "%PROCESSINGHOME%\*.*" "%FINALPRODUCTHOME%\Scripts"
	COPY %0 "%FINALPRODUCTHOME%\Scripts"
	COPY "%BASEPRJ%" "%FINALPRODUCTHOME%\Scripts"
	
	REM copy the index shapefiles for the processing layout
	MKDIR "%FINALPRODUCTHOME%\Layout_shapefiles"
	COPY "%WORKINGDIRNAME%\%RUNIDENTIFIER%_DeliveryTiles.*" "%FINALPRODUCTHOME%\Layout_shapefiles"
	COPY "%WORKINGDIRNAME%\%RUNIDENTIFIER%_ProcessingTiles.*" "%FINALPRODUCTHOME%\Layout_shapefiles"
	COPY "%WORKINGDIRNAME%\%RUNIDENTIFIER%_ProcessingBlocks.*" "%FINALPRODUCTHOME%\Layout_shapefiles"
	COPY "%WORKINGDIRNAME%\%RUNIDENTIFIER%_GroundModels.*" "%FINALPRODUCTHOME%\Layout_shapefiles"
	COPY "%WORKINGDIRNAME%\%RUNIDENTIFIER%_DensityLayers.*" "%FINALPRODUCTHOME%\Layout_shapefiles"
)

REM change back to processing home directory...important so all tasks know where they start in the directory structure
CD "%PROCESSINGHOME%"
