REM extract metrics from CSV files and merge into a single coverage
REM batch runs from processing folder for each area
REM %FILEIDENTIFIER% is the cell size identifier added to each file name
REM %CANOPYFILEIDENTIFIER% is the cell size identifier added to each file name for canopy surface models
REM %GROUNDFILEIDENTIFIER% is the cell size identifier added to each file name for ground surface models

REM build the strings used to label layers with the minimum ht, cover cutoff values, and cell size
SET MINHTLABEL=%HTCUTOFF:.=p%
SET COVERHTLABEL=%COVERCUTOFF:.=p%

REM extract elevation metrics to layers
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 5 FIRST_RETURNS_all_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 6 FIRST_RETURNS_elev_min_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 7 FIRST_RETURNS_elev_max_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 8 FIRST_RETURNS_elev_ave_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 9 FIRST_RETURNS_elev_mode_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 10 FIRST_RETURNS_elev_stddev_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 11 FIRST_RETURNS_elev_variance_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 12 FIRST_RETURNS_elev_CV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 13 FIRST_RETURNS_elev_IQ_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 14 FIRST_RETURNS_elev_skewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 15 FIRST_RETURNS_elev_kurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 16 FIRST_RETURNS_elev_AAD_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 17 FIRST_RETURNS_elev_L1_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 18 FIRST_RETURNS_elev_L2_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 19 FIRST_RETURNS_elev_L3_plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 20 FIRST_RETURNS_elev_L4_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 21 FIRST_RETURNS_elev_LCV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 22 FIRST_RETURNS_elev_Lskewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 23 FIRST_RETURNS_elev_Lkurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 24 FIRST_RETURNS_elev_P01_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 25 FIRST_RETURNS_elev_P05_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 26 FIRST_RETURNS_elev_P10_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 27 FIRST_RETURNS_elev_P20_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 28 FIRST_RETURNS_elev_P25_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 29 FIRST_RETURNS_elev_P30_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 30 FIRST_RETURNS_elev_P40_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 31 FIRST_RETURNS_elev_P50_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 32 FIRST_RETURNS_elev_P60_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 33 FIRST_RETURNS_elev_P70_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 34 FIRST_RETURNS_elev_P75_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 35 FIRST_RETURNS_elev_P80_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 36 FIRST_RETURNS_elev_P90_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 37 FIRST_RETURNS_elev_P95_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 38 FIRST_RETURNS_elev_P99_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 39 FIRST_RETURNS_r1_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1

REM skip returns 2+ (2-9 plus other, columns 40-48) since these are only first return metrics

CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 49 FIRST_RETURNS_1st_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 50 FIRST_RETURNS_all_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 51 FIRST_RETURNS_all_1st_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 52 FIRST_RETURNS_1st_cnt_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 53 FIRST_RETURNS_all_cnt_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 54 FIRST_RETURNS_1st_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 55 FIRST_RETURNS_1st_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 56 FIRST_RETURNS_all_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 57 FIRST_RETURNS_all_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 58 FIRST_RETURNS_all_1st_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 59 FIRST_RETURNS_all_1st_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 60 FIRST_RETURNS_1st_cnt_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 61 FIRST_RETURNS_1st_cnt_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 62 FIRST_RETURNS_all_cnt_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 63 FIRST_RETURNS_all_cnt_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 64 FIRST_RETURNS_pulsecnt_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 65 FIRST_RETURNS_all_cnt_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 66 FIRST_RETURNS_elev_MAD_median_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 67 FIRST_RETURNS_elev_MAD_mode_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 68 FIRST_RETURNS_elev_canopy_relief_ratio_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 69 FIRST_RETURNS_elev_quadratic_mean_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _first_returns_elevation_stats 70 FIRST_RETURNS_elev_cubic_mean_%FILEIDENTIFIER% %MULTIPLIER%

:INTENSITY
IF /I NOT "%OMITINTENSITY%"=="true" (
	REM extract intensity metrics to layers
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 6 FIRST_RETURNS_int_min_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 7 FIRST_RETURNS_int_max_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 8 FIRST_RETURNS_int_ave_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 9 FIRST_RETURNS_int_mode_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 10 FIRST_RETURNS_int_stddev_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 11 FIRST_RETURNS_int_variance_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 12 FIRST_RETURNS_int_CV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 13 FIRST_RETURNS_int_IQ_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 14 FIRST_RETURNS_int_skewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 15 FIRST_RETURNS_int_kurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 16 FIRST_RETURNS_int_AAD_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 17 FIRST_RETURNS_int_L1_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 18 FIRST_RETURNS_int_L2_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 19 FIRST_RETURNS_int_L3_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 20 FIRST_RETURNS_int_L4_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 21 FIRST_RETURNS_int_LCV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 22 FIRST_RETURNS_int_Lskewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 23 FIRST_RETURNS_int_Lkurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 24 FIRST_RETURNS_int_P01_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 25 FIRST_RETURNS_int_P05_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 26 FIRST_RETURNS_int_P10_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 27 FIRST_RETURNS_int_P20_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 28 FIRST_RETURNS_int_P25_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 29 FIRST_RETURNS_int_P30_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 30 FIRST_RETURNS_int_P40_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 31 FIRST_RETURNS_int_P50_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 32 FIRST_RETURNS_int_P60_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 33 FIRST_RETURNS_int_P70_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 34 FIRST_RETURNS_int_P75_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 35 FIRST_RETURNS_int_P80_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 36 FIRST_RETURNS_int_P90_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 37 FIRST_RETURNS_int_P95_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _first_returns_intensity_stats 38 FIRST_RETURNS_int_P99_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
)

:end

REM clear label variables
SET MINHTLABEL=
SET COVERHTLABEL=
