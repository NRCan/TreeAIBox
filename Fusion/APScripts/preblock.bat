REM Pre-processing batch file (before all blocks)

REM Environment variables defined for use:
REM    BASENAME          Base name for processing files...unique to each processing block
REM    AP_RUNDATE        Date in YYYY-MM-DD format that represents the date the job was started
REM    AP_INPUTTILES     Text file containing a list of all input tiles for the current processing block
REM    AP_RETURNDENSITY  Text file containing a list of all return density files for the current processing block
REM    AP_BAREGROUND     Text file containing a list of all bareground files for the current processing block
REM    AP_AREAMASK       Text file containing a list of all mask files for the current processing block
REM    AP_PROJECTIONFILE Name of the ESRI projection file used for all output data products
REM    AP_PROCESSINGHOME Name of the folder with auxiliary processing scripts
REM    AP_AREANAME       Area name provided in AreaProcessor
REM    AP_COORDSYSTEM    Coordinate system code provided in AreaProcessor (0=state plane, 1=UTM, 2=other)
REM    AP_COORDZONE      Coordinate system zone provided in AreaProcessor
REM    AP_LATITUDE       Latitude for the center of the area provided in AreaProcessor
REM    AP_UNITS          Measurement units provided in AreaProcessor
REM    AP_INTENSITYRANGE Range of intensity values provided in AreaProcessor
REM    AP_CLASSOPTION    Parameters for /class option provided in AreaProcessor

REM delete the file used to hold the list of block output folders
DEL "%WORKINGDIRNAME%\OutputFolders.txt"
