REM extract metrics from CSV files and merge into a single coverage
REM batch runs from processing folder for each area
REM %FILEIDENTIFIER% is the cell size identifier added to each file name
REM %CANOPYFILEIDENTIFIER% is the cell size identifier added to each file name for canopy surface models
REM %GROUNDFILEIDENTIFIER% is the cell size identifier added to each file name for ground surface models

REM build the strings used to label layers with the minimum ht, cover cutoff values, and cell size
SET MINHTLABEL=%HTCUTOFF:.=p%
SET COVERHTLABEL=%COVERCUTOFF:.=p%

REM extract elevation metrics to layers
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 5 all_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 6 elev_min_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 7 elev_max_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 8 elev_ave_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 9 elev_mode_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 10 elev_stddev_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 11 elev_variance_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 12 elev_CV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 13 elev_IQ_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 14 elev_skewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 15 elev_kurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 16 elev_AAD_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 17 elev_L1_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 18 elev_L2_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 19 elev_L3_plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 20 elev_L4_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 21 elev_LCV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 22 elev_Lskewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 23 elev_Lkurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 24 elev_P01_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 25 elev_P05_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 26 elev_P10_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 27 elev_P20_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 28 elev_P25_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 29 elev_P30_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 30 elev_P40_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 31 elev_P50_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 32 elev_P60_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 33 elev_P70_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 34 elev_P75_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 35 elev_P80_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 36 elev_P90_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 37 elev_P95_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 38 elev_P99_%MINHTLABEL%plus_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 39 r1_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 40 r2_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 41 r3_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 42 r4_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 43 r5_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 44 r6_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 45 r7_cnt_%MINHTLABEL%plus_%FILEIDENTIFIER% 1

REM skip returns 8+ (8-9 plus other, columns 46-48)

CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 49 1st_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 50 all_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 51 all_1st_cover_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 52 1st_cnt_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 53 all_cnt_above%COVERHTLABEL%_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 54 1st_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 55 1st_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 56 all_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 57 all_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 58 all_1st_cover_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 59 all_1st_cover_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 60 1st_cnt_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 61 1st_cnt_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 62 all_cnt_above_mean_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 63 all_cnt_above_mode_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 64 pulsecnt_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 65 all_cnt_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 66 elev_MAD_median_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 67 elev_MAD_mode_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 68 elev_canopy_relief_ratio_%FILEIDENTIFIER% 1
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 69 elev_quadratic_mean_%FILEIDENTIFIER% %MULTIPLIER%
CALL "%PROCESSINGHOME%\extract_metric" _all_returns_elevation_stats 70 elev_cubic_mean_%FILEIDENTIFIER% %MULTIPLIER%

:INTENSITY
IF /I NOT "%OMITINTENSITY%"=="true" (
	REM extract intensity metrics to layers
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 6 int_min_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 7 int_max_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 8 int_ave_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 9 int_mode_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 10 int_stddev_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 11 int_variance_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 12 int_CV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 13 int_IQ_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 14 int_skewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 15 int_kurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 16 int_AAD_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 17 int_L1_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 18 int_L2_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 19 int_L3_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 20 int_L4_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 21 int_LCV_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 22 int_Lskewness_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 23 int_Lkurtosis_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 24 int_P01_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 25 int_P05_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 26 int_P10_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 27 int_P20_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 28 int_P25_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 29 int_P30_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 30 int_P40_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 31 int_P50_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 32 int_P60_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 33 int_P70_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 34 int_P75_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 35 int_P80_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 36 int_P90_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 37 int_P95_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
	CALL "%PROCESSINGHOME%\extract_metric" _all_returns_intensity_stats 38 int_P99_%MINHTLABEL%plus_%FILEIDENTIFIER% 1
)

:end

REM clear label variables
SET MINHTLABEL=
SET COVERHTLABEL=
