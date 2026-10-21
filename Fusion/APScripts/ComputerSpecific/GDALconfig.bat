REM This batch file sets the location of the GDAL translate utility used to convert ASCII raster and other format files to IMAGINE format.
REM This information is specific to each computer and we have isolated the configuration script to make it easier to update AreaProcessor scipts
REM without overwriting this information.

REM file specifier for gdal_translate (don't need the ".exe")...include the full path and drive letter...DO NOT enclose the path in quotation marks
SET GDAL_TRANSLATE_LOCATION=C:\Program Files\GDAL\gdal_translate

REM Older version of GDAL had a gdal-data folder. It seems that newer version do a better job of hiding this folder. Try searching for files named
REM "gcs.csv" to find the correct folder then set the GDAL_DATA variable to this folder.
SET GDAL_DATA=C:\Program Files\GDAL\gdal-data
