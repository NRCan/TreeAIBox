REM convert output ASCII raster files to Imagine format
REM %1 full input filename with extension, drive letter, and folder for ASCII raster file
REM %2 output folder...no closing "\"...does not check to make sure output folder exists

IF /I "%CONVERTTOIMG%"=="true" (
	"%GDAL_TRANSLATE_LOCATION%" -a_srs "%~dpn1.prj" -of HFA -co COMPRESSED=YES "%~1" "%~2\%~n1.img"

	REM delete the XML file created by gdal_translate...this file may not always be created
	DEL "%~2\%~n1.img.aux.xml"

	REM make sure the .img file was created, then delete the .asc file and .prj file
	IF EXIST "%~2\%~n1.img" (
		IF /I NOT "%KEEPASCIIFILES%"=="true" (
			DEL "%~1"
			DEL "%~dpn1.prj"
		)
	)
)
