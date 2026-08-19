REM **************************************************************************************************************
REM *****             setup batch file used in conjunction with FUSION's AreaProcessor tool                  *****
REM *****                                                                                                    *****
REM *****     Used to set up folder structure for data and variables to control run for producing return     *****
REM *****                                density layers from point data                                      *****
REM **************************************************************************************************************

REM flag to control conversion of all outputs to IMAGINE format. The default format is FUSION DTM format. IMAGINE format is much more compact
REM and the files contain embedded projection information. projection info for ASCII raster files is help in a separate .PRJ file.
REM if CONVERTTOIMG is FALSE, output will be FUSION DTM format for use in AreaProcessor and other FUSION programs
REM if CONVERTTOIMG is TRUE, output will be in Erdas Imagine format
SET CONVERTTOIMG=FALSE

REM flag to delete intermediate ASCII raster files and intermediate BMP files (intensity images). You can set this to TRUE to keep the "fluffy" files
REM but they use up quite a bit of disk space.
SET KEEPASCIIFILES=FALSE

REM ###########################################################
REM           Pick up variables from AreaProcessor...we won't use all of these
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
REM           Parameters for processing
REM ###########################################################

REM pick up cell size 
SET CELLSIZE=%AP_ALIGNMENT_CELLSIZE%

REM ###########################################################
REM           Labels for output folders and files
REM ###########################################################
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

REM Set up a file to record output folders for all blocks. As blocks are processed, the output folder will be added to the file.
REM The post-block processing script will use this list to build a list of outputs for the blocks. We expect this file to only get
REM some of the block output folders for multi-process jobs since different processes will try to write to the file at the same time.
REM This is OK as we only need the name of one output folder (block) to build the list of outputs for the final merges.
ECHO %PRODUCTHOME%>>"%WORKINGDIRNAME%\OutputFolders.txt"

REM ###########################################################
REM           Create directory structure for outputs
REM ###########################################################
CD "%WORKINGDIRNAME%"
REM MKDIR "%PRODUCTHOME%"
REM MKDIR "%PRODUCTHOME%\Metrics_%FILEIDENTIFIER%"

REM create directory structure for final outputs
REM we always need the home folder because we copy the batch files into a subfolder
MKDIR "%FINALPRODUCTHOME%"
IF NOT "%BLOCKNAME%"=="" (
   REM create directory structure for merged outputs
   MKDIR "%FINALPRODUCTHOME%\Metrics_%FILEIDENTIFIER%"
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
)

REM change back to processing home directory...important so all tasks know where they start in the directory structure
CD "%PROCESSINGHOME%"
