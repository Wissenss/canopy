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

Third party systems may benefit from this sort of information, this command aims to provide a way for that data to be ingested by **RDMS**. Basically this constructs an `UPDATE` query so you can save this information to your favorite database.

This is only a provisional solution, you should implement a way for your system to ingest **\*.csv** files, that way you may control every kind of transformation specific to your system.

```bash
canopy.exe query "./animal_i_have_become.mp3" --output "./query.sql" --table-name "songs" --
```

This produces the query:

```sql
UPDATE songs SET vocal_start = 26 AND vocals_end = 241 WHERE song_id = 2;
```