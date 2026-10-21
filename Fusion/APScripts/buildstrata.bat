REM extract strata metrics from CSV files and merge into a single coverage for each layer and metric
REM this batch file shouldn't be called unless the user specified that they were doing strata metrics in the setup batch file

REM enable delayed expansion of environment variable to allow us to change variables in a loop
SETLOCAL ENABLEDELAYEDEXPANSION

REM step through the strata...label the strata using the bottom and top heights
SET STRATABOTTOM=0
SET STRATA=1

REM parse strata breaks and build name for the strata
FOR %%i IN (%STRATAHEIGHTS%) DO (
	SET STRATATOP=%%i
	SET STRATALABEL=!STRATABOTTOM:.=p!to!STRATATOP:.=p!%UNITS:~0,1%
	CALL "%PROCESSINGHOME%\extract_strata_layer" !STRATA! !STRATALABEL!
	SET /A STRATA=!STRATA!+1
	SET STRATABOTTOM=%%i
)
REM make last call for the final strata
SET STRATALABEL=!STRATABOTTOM:.=p!%UNITS:~0,1%_plus
CALL "%PROCESSINGHOME%\extract_strata_layer" !STRATA! !STRATALABEL!

ENDLOCAL

SET STRATABOTTOM=
SET STRATATOP=
SET STRATA=
SET STRATALABEL=
