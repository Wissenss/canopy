import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from cyclopts import App
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn
from banner import print_banner
from version import __version__
from query_builder import TAG_COUNT, cue_values, pattern_tags, build_query

app = App(name="canopy", version=__version__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg"}
TABLE_EXTENSIONS = {".csv", ".xls", ".xlsx"}

def _list_audio_files(file_path: Path, recursive: bool) -> list[Path]:
    """
        returns the audio files in file_path when it is a directory, or file_path itself otherwise.
    """

    if not file_path.is_dir():
        return [file_path]

    pattern = "**/*" if recursive else "*"
    return sorted(f for f in file_path.glob(pattern) if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)

def _print_params(console: Console, params: list[tuple[str, str]]):
    """
        logs the parameters used for this run.
    """

    params_table = Table(box=None, show_header=False, pad_edge=False)
    params_table.add_column(style="bold blue", no_wrap=True)
    params_table.add_column()
    for key, value in params:
        params_table.add_row(key, value)
    console.print(params_table)
    console.print()

def _cue_options(window: int, min_db: float, min_relative_db: float | None, min_sustain: float, min_sustain_interval: float) -> dict:
    """
        returns the get_vocal_cues keyword arguments for the audio processing options.
    """

    return {"analisis_window": window, "min_vocals_db": min_db, "min_relative_db": min_relative_db, "min_sustain": min_sustain, "min_sustain_interval": min_sustain_interval}

def _cue_params(window: int, min_db: float, min_relative_db: float | None, min_sustain: float, min_sustain_interval: float) -> list[tuple[str, str]]:
    """
        returns the audio processing options as (name, value) pairs to log.
    """

    return [
        ("window", f"{window} s"),
        ("min_db", f"{min_db} dBFS"),
        ("min_relative_db", f"{min_relative_db} dB below peak" if min_relative_db is not None else "-"),
        ("min_sustain", f"{min_sustain} s"),
        ("min_sustain_interval", f"{min_sustain_interval} s"),
    ]

def _analyze_files(console: Console, files: list[Path], cue_options: dict, silent: bool):
    """
        runs get_vocal_cues (with cue_options as keyword arguments) on each file showing the progress and a results table.

        yields (index, file, v_s, v_e, elapsed, finished_at) for each file processed successfully, index is the position in files.
    """

    columns = (TextColumn("{task.description}"), BarColumn(complete_style="blue", finished_style="blue", pulse_style="blue"), MofNCompleteColumn(), TimeElapsedColumn())

    with Progress(*columns, console=console, disable=silent) as progress:
        model_task = progress.add_task("loading model", total=None)
        from vocal_cues import get_vocal_cues # lazy import, loading the demucs model is slow
        progress.remove_task(model_task)

        # results are printed as they come, each row as a table with fixed widths so the columns align
        # the file column fits the longest path, but shrinks in narrow consoles (19 + 3 * 9 fixed columns + 4 * 2 padding)
        file_w = max(len("file"), min(max(len(str(f)) for f in files), progress.console.width - 54))

        def row_table(show_header: bool = False) -> Table:
            table = Table(box=None, show_header=show_header, header_style="bold blue", pad_edge=False)
            table.add_column("finished_at", width=19, no_wrap=True)
            table.add_column("file", width=file_w, no_wrap=True, overflow="ellipsis")
            table.add_column("v_s (s)", width=9, justify="right", no_wrap=True)
            table.add_column("v_e (s)", width=9, justify="right", no_wrap=True)
            table.add_column("took (s)", width=9, justify="right", no_wrap=True)
            return table

        progress.console.print(row_table(show_header=True))

        files_task = progress.add_task("analyzing", total=len(files))
        for i, f in enumerate(files):
            progress.update(files_task, description=f"analyzing {f.name}")
            start = time.perf_counter()
            try:
                v_s, v_e = get_vocal_cues(str(f), **cue_options)
            except Exception as exc:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {str(f):<{file_w}}  error: {exc} ({time.perf_counter() - start:.2f}s)", file=sys.stderr)
                continue
            finally:
                progress.advance(files_task)

            elapsed = time.perf_counter() - start
            finished_at = f"{datetime.now():%Y-%m-%d %H:%M:%S}"

            row = row_table()
            row.add_row(finished_at, str(f), f"{v_s:.3f}", f"{v_e:.3f}", f"{elapsed:.2f}")
            progress.console.print(row)

            yield i, f, v_s, v_e, elapsed, finished_at

        progress.update(files_task, description="done")

@app.command
def vocal_cues(file_path: Path, output: Path | None = None, window: int = 60, min_db: float = -18, min_relative_db: float | None = None, min_sustain: float = 0,
               min_sustain_interval: float = 0, recursive: bool = False, silent: bool = False):
    """
    Prints the second when the voice starts / ends in the given audio file(s).

    Parameters
    ----------
    file_path
        Audio file to analyze, or a directory with audio files.
    output
        Optional .csv or .txt file to store the results.
    window
        Seconds analyzed at the start / end of each file.
    min_db
        Vocals level (dBFS) considered voice.
    min_relative_db
        Vocals up to this many dB below the vocals peak are considered voice, can be used along --min-db.
    min_sustain
        Seconds the vocals must last to be considered the start / end.
    min_sustain_interval
        Seconds of silence tolerated between vocals for --min-sustain, 0 = continuous vocals.
    recursive
        When file_path is a directory, also look in its subdirectories.
    silent
        Disables the banner and progress indicators.
    """

    console = Console()

    if not silent:
        print_banner(console)

    files = _list_audio_files(file_path, recursive)

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("file_path", str(file_path)),
        ("files", str(len(files))),
        ("output", str(output) if output is not None else "-"),
        *_cue_params(window, min_db, min_relative_db, min_sustain, min_sustain_interval),
        ("recursive", str(recursive)),
        ("silent", str(silent)),
    ]
    _print_params(console, params)

    if not files:
        print(f"no audio files found in {file_path}", file=sys.stderr)
        return

    out_file = None
    writer = None
    if output is not None:
        out_file = open(output, "w", newline="", encoding="utf-8")

        # parameters as '#' comment lines (pandas: read_csv(..., comment="#"))
        for key, value in params:
            out_file.write(f"# {key}: {value}\n")
        out_file.write("\n")

        if output.suffix.lower() == ".csv":
            writer = csv.writer(out_file)
            writer.writerow(["file", "vocals_start", "vocals_end", "processing_time", "finished_at"])

    try:
        cue_options = _cue_options(window, min_db, min_relative_db, min_sustain, min_sustain_interval)
        for _, f, v_s, v_e, elapsed, finished_at in _analyze_files(console, files, cue_options, silent):
            if writer is not None:
                writer.writerow([str(f), f"{v_s:.3f}", f"{v_e:.3f}", f"{elapsed:.2f}", finished_at])
            elif out_file is not None:
                out_file.write(f"file: {f}\nvocals_start: {v_s:.3f}\nvocals_end: {v_e:.3f}\nprocessing_time: {elapsed:.2f}\nfinished_at: {finished_at}\n\n")

            if out_file is not None:
                out_file.flush()
    finally:
        if out_file is not None:
            out_file.close()

def _find_column(header: list[str], name: str) -> int:
    """
        returns the index of the column name in header (case insensitive), raises ValueError if missing.
    """

    names = [h.strip().lower() for h in header]
    try:
        return names.index(name.strip().lower())
    except ValueError:
        raise ValueError(f"column '{name}' not found, available columns: {', '.join(h.strip() for h in header)}") from None

def _cell_to_str(value) -> str:
    """
        converts an excel cell value to text, whole numbers lose the '.0' excel adds (2990.0 -> '2990').
    """

    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)

def _read_rows(path: Path):
    """
        yields the rows (list of str) of the first sheet of a .xls / .xlsx file or of a .csv file (utf-8, falling back to the windows ansi codepage).
    """

    suffix = path.suffix.lower()

    if suffix == ".xls":
        import xlrd
        sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
        for r in range(sheet.nrows):
            yield [_cell_to_str(v) for v in sheet.row_values(r)]
        return

    if suffix == ".xlsx":
        import openpyxl
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            for row in workbook.worksheets[0].iter_rows(values_only=True):
                yield [_cell_to_str(v) for v in row]
        finally:
            workbook.close()
        return

    # csv files saved by excel on spanish windows are usually cp1252, not utf-8
    try:
        with open(path, newline="", encoding="utf-8-sig") as file:
            rows = list(csv.reader(file))
    except UnicodeDecodeError:
        with open(path, newline="", encoding="cp1252") as file:
            rows = list(csv.reader(file))

    yield from rows

def _read_csv_entries(csv_path: Path, base_path: Path | None = None, file_column: str | None = None, value_columns: dict[int, str] | None = None) -> list[tuple[Path, dict[int, str]]]:
    """
        reads the (audio file, {N: csv_val_N}) pairs from csv_path.

        without column names the first column is the file and the header row is optional (skipped when its first cell is not an audio file);
        with column names (file_column / value_columns) the first row must be the header, a missing file_column falls back to the first column.
        blank lines and '#' lines are skipped; relative audio paths are resolved from base_path, if given.
    """

    if value_columns is None:
        value_columns = {}

    use_header = file_column is not None or bool(value_columns)
    file_idx = 0
    value_idx = {}
    header_read = False

    entries = []
    for line_no, row in enumerate(_read_rows(csv_path), start=1):
        if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
            continue

        if not header_read:
            header_read = True
            if use_header:
                if file_column is not None:
                    file_idx = _find_column(row, file_column)
                value_idx = {n: _find_column(row, name) for n, name in value_columns.items()}
                continue
            if Path(row[0].strip()).suffix.lower() not in AUDIO_EXTENSIONS:
                continue

        if len(row) <= max([file_idx, *value_idx.values()]):
            print(f"{csv_path}:{line_no}: missing columns, skipped", file=sys.stderr)
            continue

        audio_path = Path(row[file_idx].strip())
        if base_path is not None and not audio_path.is_absolute():
            audio_path = base_path / audio_path

        entries.append((audio_path, {n: row[idx].strip() for n, idx in value_idx.items()}))

    return entries

@app.command
def query(file_path: Path, *, pattern: str, output: Path = Path("output.sql"), base_path: Path | None = None, csv_file_column: str | None = None, recursive: bool = False,
          window: int = 60, min_db: float = -18, min_relative_db: float | None = None, min_sustain: float = 0, min_sustain_interval: float = 0, silent: bool = False,
          val_1: str | None = None, val_2: str | None = None, val_3: str | None = None, val_4: str | None = None,
          val_5: str | None = None, val_6: str | None = None, val_7: str | None = None, val_8: str | None = None,
          csv_val_1_column: str | None = None, csv_val_2_column: str | None = None, csv_val_3_column: str | None = None, csv_val_4_column: str | None = None,
          csv_val_5_column: str | None = None, csv_val_6_column: str | None = None, csv_val_7_column: str | None = None, csv_val_8_column: str | None = None):
    """
    Generates one query per audio file replacing the #tags# of pattern with the vocals start / end and the given values.

    Parameters
    ----------
    file_path
        Audio file, directory with audio files or .csv / .xls / .xlsx file with the audio file paths.
    pattern
        Query pattern, tags: #file_name#, #vocals_start_s#, #vocals_start_ms#, #vocals_end_s#, #vocals_end_ms#, #val_N#, #csv_val_N# (N = 1..8).
    output
        .sql file to write the queries to.
    base_path
        Folder the relative audio paths in the csv are relative to, by default the paths are used as is.
    csv_file_column
        Name of the csv column with the audio file path, by default the first column.
    recursive
        When file_path is a directory, also look in its subdirectories.
    window
        Seconds analyzed at the start / end of each file.
    min_db
        Vocals level (dBFS) considered voice.
    min_relative_db
        Vocals up to this many dB below the vocals peak are considered voice, can be used along --min-db.
    min_sustain
        Seconds the vocals must last to be considered the start / end.
    min_sustain_interval
        Seconds of silence tolerated between vocals for --min-sustain, 0 = continuous vocals.
    silent
        Disables the banner and progress indicators.
    val_1
        Value of the #val_1# tag.
    val_2
        Value of the #val_2# tag.
    val_3
        Value of the #val_3# tag.
    val_4
        Value of the #val_4# tag.
    val_5
        Value of the #val_5# tag.
    val_6
        Value of the #val_6# tag.
    val_7
        Value of the #val_7# tag.
    val_8
        Value of the #val_8# tag.
    csv_val_1_column
        Name of the csv column whose value replaces the #csv_val_1# tag.
    csv_val_2_column
        Name of the csv column whose value replaces the #csv_val_2# tag.
    csv_val_3_column
        Name of the csv column whose value replaces the #csv_val_3# tag.
    csv_val_4_column
        Name of the csv column whose value replaces the #csv_val_4# tag.
    csv_val_5_column
        Name of the csv column whose value replaces the #csv_val_5# tag.
    csv_val_6_column
        Name of the csv column whose value replaces the #csv_val_6# tag.
    csv_val_7_column
        Name of the csv column whose value replaces the #csv_val_7# tag.
    csv_val_8_column
        Name of the csv column whose value replaces the #csv_val_8# tag.
    """

    console = Console()

    if not silent:
        print_banner(console)

    vals = {n: v for n, v in enumerate((val_1, val_2, val_3, val_4, val_5, val_6, val_7, val_8), start=1) if v is not None}
    csv_columns = {n: c for n, c in enumerate((csv_val_1_column, csv_val_2_column, csv_val_3_column, csv_val_4_column,
                                               csv_val_5_column, csv_val_6_column, csv_val_7_column, csv_val_8_column), start=1) if c is not None}
    is_table = file_path.suffix.lower() in TABLE_EXTENSIONS

    # every #val_N# / #csv_val_N# tag in the pattern needs its value
    tags = pattern_tags(pattern)
    missing = [f"--val-{n}" for n in range(1, TAG_COUNT + 1) if f"val_{n}" in tags and n not in vals]
    missing += [f"--csv-val-{n}-column" for n in range(1, TAG_COUNT + 1) if f"csv_val_{n}" in tags and n not in csv_columns]
    if missing:
        print(f"the pattern uses tags without value, missing: {', '.join(missing)}", file=sys.stderr)
        return
    if csv_columns and not is_table:
        print("--csv-val-N-column options require file_path to be a .csv / .xls / .xlsx file", file=sys.stderr)
        return

    if is_table:
        try:
            entries = _read_csv_entries(file_path, base_path, csv_file_column, csv_columns)
        except Exception as exc:
            print(f"{file_path}: {exc}", file=sys.stderr)
            return
    else:
        entries = [(f, {}) for f in _list_audio_files(file_path, recursive)]

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("file_path", str(file_path)),
        ("files", str(len(entries))),
        ("pattern", pattern),
        ("output", str(output)),
        *((f"val_{n}", v) for n, v in vals.items()),
        *((f"csv_val_{n}_column", c) for n, c in csv_columns.items()),
    ]
    if is_table:
        params += [
            ("base_path", str(base_path) if base_path is not None else "-"),
            ("csv_file_column", csv_file_column if csv_file_column is not None else "1st column"),
        ]
    else:
        params.append(("recursive", str(recursive)))
    params += [
        *_cue_params(window, min_db, min_relative_db, min_sustain, min_sustain_interval),
        ("silent", str(silent)),
    ]
    _print_params(console, params)

    if not entries:
        print(f"no audio files found in {file_path}", file=sys.stderr)
        return

    with open(output, "w", encoding="utf-8") as out_file:
        # parameters as sql comment lines
        for key, value in params:
            out_file.write(f"-- {key}: {value}\n")
        out_file.write("\n")

        files = [audio_path for audio_path, _ in entries]
        cue_options = _cue_options(window, min_db, min_relative_db, min_sustain, min_sustain_interval)
        for i, f, v_s, v_e, _, _ in _analyze_files(console, files, cue_options, silent):
            if v_s == 0 and v_e == 0:
                out_file.write(f"-- {f}: no vocals found\n")
                out_file.flush()
                continue

            values = {
                **cue_values(v_s, v_e),
                "file_name": f.name,
                **{f"val_{n}": v for n, v in vals.items()},
                **{f"csv_val_{n}": v for n, v in entries[i][1].items()},
            }
            out_file.write(build_query(pattern, values) + "\n")
            out_file.flush()

if __name__ == "__main__":
    app()
