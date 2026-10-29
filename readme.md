# Canopy

A self-contained music analyser command line interface, use this tool to extract the following features from audio files:

- vocal-cues (when singing start / ends)

## Usage

As a typical cli, canopy takes a command and a list of options as arguments:

```bash
canopy.exe [COMMAND] [OPTIONS]
```

Next, what each command does, the list of options it supports and a couple of examples:

### vocal-cues command

Process the given audio file and return when singing starts / end. 

```bash
canopy.exe vocal-cues "./animal_i_have_become.mp3" 
```

Processing a whole directory with a threshold relative to each song's vocals level, ignoring vocals shorter than 2 seconds:

```bash
canopy.exe vocal-cues "./music" --min-db -40 --min-relative-db 20 --min-sustain 2 --min-sustain-interval 0.3 --output "./results.csv"
```

#### options

`--file-path [path]` : the path for an audio file or directory, if `[path]` is a directory then all audio files in that directory will be processed. This is a required argument.

`--recursive [bool]` : if the provided `--file-path` is a directory, weather or not to look for audio files in subdirectories. Default `False`.

`--output [path]` : the file path in which to save the processing results, for now only `*.txt` and `*.csv` files are valid file types. Default `""`, no file output.

`--window [span]` : the time `[span]` in seconds to analyse, that is if `[span]` is `60`, then the first and last 60 seconds will be analysed looking for vocal start and end. Default `60`.

`--min-db [db]` : `[db]` threashold to consider a sound in the vocals track, this controls how sensitive or not the filtering is. Default `-18` db.

`--min-relative-db [db]` : a sound in the vocals track is considered voice when it is at most `[db]` below the loudest point of the vocals track (taken from both analysed windows), so the threshold adapts to each song's level. It can be used together with `--min-db`, then a sound must pass both thresholds; to use only the relative threshold set `--min-db` very low (e.g. `-100`). Default: not used.

`--min-sustain [span]` : the vocals must last at least `[span]` seconds to be considered the start / end, this filters short spikes (a breath, a shout, an ad-lib) before the singing actually starts. Default `0`, any sound counts.

`--min-sustain-interval [span]` : the silence in seconds tolerated between vocals so they still count as one for `--min-sustain`, that is with `--min-sustain 3 --min-sustain-interval 0.5` the vocals must last 3 seconds without pauses longer than half a second. Default `0`, the vocals must be continuous.

`--silent [bool]` : weather or not to show the banner and progress indicators, the results are still printed. Default `False`. 

### query command

Third-party systems may benefit from the information extracted by Canopy. The query command provides a way to integrate this data into **RDMS** by generating query strings that can be executed against your database.

This command generates a query by replacing predefined placeholders in a user-provided pattern with the corresponding values extracted from audio files or supplied through command-line arguments.

This is a provisional integration solution. For production use, it is recommended to implement a mechanism for ingesting **\*.csv** files directly into your system. This approach provides greater flexibility and allows you to handle any transformations required by your application's data model.

```bash
canopy.exe query "./animal_i_have_become.mp3" --pattern "UPDATE songs SET v_s = #vocals_start_s#, v_e = #vocals_end_s# WHERE song_id = #val_1#;" --val-1 2
```

This produces the query:

```sql
UPDATE songs SET v_s = 26, v_e = 241 WHERE song_id = 2;
```

The console shows the same progress and results as the vocal-cues command, while the queries are written to a **\*.sql** file (see `--output`), one line per audio file. The run parameters are written at the top of the file as `--` comments, and audio files where no vocals are found are written as a `--` comment instead of a query.

#### options

`--file-path [path]` : the path for an audio file, directory or **\*.csv** file (**\*.xls** and **\*.xlsx** files are also supported). If `[path]` is a directory then all audio files in that directory will be processed. If `[path]` is a **\*.csv** file, each row is an audio file to process; blank lines and lines starting with `#` are skipped. This is a required argument.

`--recursive [bool]` : if the provided `--file-path` is a directory, weather or not to look for audio files in subdirectories. Default `False`.

`--csv-file-column [name]` : if `--file-path` is a **\*.csv** file, the name of the column with the audio file path. Default: the first column.

`--base-path [path]` : if `--file-path` is a **\*.csv** file, the folder relative audio paths are resolved from. Default `""`, the audio paths are used as they are in the **\*.csv** file.

`--csv-val-1-column [name]` : if `--file-path` is a **\*.csv** file this columns value will be used to replace the tag `"#csv_val_1#"` in the providen `--pattern`. There are 8 variations of this argument with similar behaviour: `--csv-val-2-column`, `--csv-val-3-column` and so on.

When `--csv-file-column` or any `--csv-val-N-column` is given, the first row of the **\*.csv** file must be a header with the column names (case insensitive). Otherwise the header row is optional.

`--val-1 [value]` : the value to replace the tag **#val_1#** in the providen `--pattern`. There are 8 variations of this argument with similar behaviour: `--val-2`, `--val-3` and so on.

`--pattern [patter]` : the pattern to use for query generation, one line per audio will be created using this pattern and replacing the tags, if any. The follwing tags are available:
- **#file_name#** the audio file name, with its extension and without its folder (`animal_i_have_become.mp3`).
- **#vocals_start_s#** the vocals start in seconds (rounded to whole seconds).
- **#vocals_start_ms#** the vocals start in miliseconds.
- **#vocals_end_s#** the vocals end in seconds (rounded to whole seconds).
- **#vocals_end_ms#** the vocals end in miliseconds.
- **#val_1#** the providen `--val-1` value. There are eight variations of this field with similar behaviour: **#val_2#**, **#val_3#** and so on.
- **#csv_val_1#** the providen `--csv-val-1-column` column value if `--file-path` is a **\*.csv** file. There are eight variations of this field with similar behaviour: **#csv_val_2#**, **#csv_val_3#** and so on.

If the pattern uses a **#val_N#** or **#csv_val_N#** tag without its option, the command fails before processing any file.

`--output [path]` : the **\*.sql** file path in which to save the queries. Default `./output.sql`.

`--window [span]` : the time `[span]` in seconds to analyse, that is if `[span]` is `60`, then the first and last 60 seconds will be analysed looking for vocal start and end. Default `60`.

`--min-db [db]` : `[db]` threashold to consider a sound in the vocals track, this controls how sensitive or not the filtering is. Default `-18` db.

`--min-relative-db [db]`, `--min-sustain [span]`, `--min-sustain-interval [span]` : same as in the [vocal-cues command](#options).

`--silent [bool]` : weather or not to show the banner and progress indicators. Default `False`.

#### examples

