"%~dp0canopy.exe" query ^
--file-path "%~dp0rolas.xls" ^
--pattern "UPDATE cartuchos SET TiempoEntrada = #vocals_start_ms# WHERE CartuchoId = #csv_val_1# AND TipoContenido = 3;" ^
--csv-file-column "Archivo" ^
--base-path "Q:\\Audios.base.pruebas" ^
--csv-val-1-column "CartuchoId" ^
--output "%~dp0entrada.sql" ^
--window 120 ^
--min-db -18 
