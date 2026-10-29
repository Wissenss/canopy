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

#### options

`--file-path [path]` : the path for an audio file or directory, if `[path]` is a directory then all audio files in that directory will be processed. This is a required argument.

`--recursive [bool]` : if the provided `--file-path` is a directory, weather or not to look for audio files in subdirectories. Default `False`.

`--output [path]` : the file path in which to save the processing results, for now only `*.txt` and `*.csv` files are valid file types. Default `""`, no file output.

`--window [span]` : the time `[span]` in seconds to analyse, that is if `[span]` is `60`, then the first and last 60 seconds will be analysed looking for vocal start and end. Default `60`.

`--min-db [db]` : `[db]` threashold to consider a sound in the vocals track, this controls how sensitive or not the filtering is. Default `-40` db.

`--silent [bool]` : weather or not to output text to the console. Default `True`. 

### query command

Third-party systems may benefit from the information extracted by Canopy. The query command provides a way to integrate this data into **RDMS** by generating query strings that can be executed against your database.

This command generates a query by replacing predefined placeholders in a user-provided pattern with the corresponding values extracted from audio files or supplied through command-line arguments.

This is a provisional integration solution. For production use, it is recommended to implement a mechanism for ingesting **\*.csv** files directly into your system. This approach provides greater flexibility and allows you to handle any transformations required by your application's data model.

```bash
canopy.exe query "./animal_i_have_become.mp3" --pattern "UPDATE songs SET s_v = #vocals_start_s#, s_e = #vocals_end_s# WHERE song_id = #val_1#" --val-1 2
```

This produces the query:

```sql
UPDATE songs SET v_s = 26 AND v_e = 241 WHERE song_id = 2;
```

#### options

`--file-path [path]` : the path for an audio file, directory or **\*.csv** file. This is a required argument.

`--csv-val-1-column` : if `--file-path` is a **\*.csv** file this columns value will be used to replace the tag `"#csv_val_1#"` in the providen `--pattern`. There are 8 variations of this argument with similar behaviour: `--csv-val-2-column`, `--csv-val-3-column` and so on.

`--val-1` : the value to replace the tag **#val_1#** in the providen `--pattern`. There are 8 variations of this argument with similar behaviour: `--val-2`, `--val-3` and so on.

`--pattern [patter]` : the pattern to use for query generation, one line per audio will be created using this pattern and replacing the tags, if any. The follwing tags are available:
- **#vocals_start_s#** the vocals start in seconds.
- **#vocals_start_ms#** the vocals start in miliseconds.
- **#vocals_end_s#** the vocals end in seconds.
- **#vocals_end_ms#** the vocals end in miliseconds.
- **#val_1#** the providen `--val-1` value. There are eight variations of this field with similar behaviour: **#val_2#**, **#val_3#** and so on.
- **#csv_val_1#** the providen `--csv-val-1-column` column value if `--file-path` is a **\*.csv** file. There are eight variations of this field with similar behaviour: **#csv_val_2#**, **#csv_val_3#** and so on.