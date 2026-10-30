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
from data_ingestor import CSV_EXTENSIONS, EXCEL_EXTENSIONS, Data, DataIngestor
from data_exporter import DataExporter

app = App(name="canopy", version=__version__)

TABLE_EXTENSIONS = CSV_EXTENSIONS | EXCEL_EXTENSIONS

def _ingest(path: Path, recursive: bool, base_path: Path | None = None, file_column: str | None = None, vals: dict[int, str] | None = None,
            columns: dict[int, str] | None = None) -> list[Data]:
    """
        returns the Data (audio file + val_N) to process from path, see DataIngestor.

        vals are the val_N defaults and columns the table column names val_N take their value from, both keyed by N.
    """

    ingestor = DataIngestor()
    ingestor.path = path
    ingestor.recursive = recursive
    ingestor.base_path = base_path
    ingestor.tbl_col_name_file_path = file_column or ""
    for n, v in (vals or {}).items():
        setattr(ingestor, f"val_{n}", v)
    for n, c in (columns or {}).items():
        setattr(ingestor, f"tbl_col_name_val_{n}", c)
    return ingestor.ingest()

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
def vocal_cues(input: Path, output: Path | None = None, output_two: Path | None = None, output_three: Path | None = None, window: int = 60, min_db: float = -18,
               min_relative_db: float | None = None, min_sustain: float = 0, min_sustain_interval: float = 0, recursive: bool = False, silent: bool = False):
    """
    Prints the second when the voice starts / ends in the given audio file(s).

    Parameters
    ----------
    input
        Audio file to analyze, directory with audio files or .csv / .xls / .xlsx file with the audio file paths in its first column.
    output
        Optional .csv, .txt or .xlsx file to store the results.
    output_two
        Optional second .csv, .txt or .xlsx file to store the results.
    output_three
        Optional third .csv, .txt or .xlsx file to store the results.
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
        When input is a directory, also look in its subdirectories.
    silent
        Disables the banner and progress indicators.
    """

    console = Console()

    if not silent:
        print_banner(console)

    try:
        entries = _ingest(input, recursive)
    except Exception as exc:
        print(f"{input}: {exc}", file=sys.stderr)
        return
    files = [d.file_path for d in entries]

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("input", str(input)),
        ("files", str(len(files))),
        ("output", str(output) if output is not None else "-"),
        ("output_two", str(output_two) if output_two is not None else "-"),
        ("output_three", str(output_three) if output_three is not None else "-"),
        *_cue_params(window, min_db, min_relative_db, min_sustain, min_sustain_interval),
        ("recursive", str(recursive)),
        ("silent", str(silent)),
    ]
    _print_params(console, params)

    if not files:
        print(f"no audio files found in {input}", file=sys.stderr)
        return

    # one exporter per output, all are created before processing so an invalid output fails early
    exporters = []
    for path in (output, output_two, output_three):
        if path is None:
            continue
        exporter = DataExporter()
        exporter.path = path
        exporter.params = params
        try:
            exporter.begin_writing()
        except Exception as exc:
            print(exc, file=sys.stderr)
            for e in exporters:
                e.end_writing()
            return
        exporters.append(exporter)

    try:
        cue_options = _cue_options(window, min_db, min_relative_db, min_sustain, min_sustain_interval)
        for i, _, v_s, v_e, elapsed, finished_at in _analyze_files(console, files, cue_options, silent):
            data = entries[i]
            data.v_p = True
            data.v_s = v_s
            data.v_e = v_e
            data.processing_time = elapsed
            data.finished_at = finished_at

            for exporter in exporters:
                exporter.write(data)
    finally:
        for exporter in exporters:
            exporter.end_writing()

@app.command
def query(input: Path, *, pattern: str, output: Path = Path("output.sql"), base_path: Path | None = None, csv_file_column: str | None = None, recursive: bool = False,
          window: int = 60, min_db: float = -18, min_relative_db: float | None = None, min_sustain: float = 0, min_sustain_interval: float = 0, silent: bool = False,
          val_1: str | None = None, val_2: str | None = None, val_3: str | None = None, val_4: str | None = None,
          val_5: str | None = None, val_6: str | None = None, val_7: str | None = None, val_8: str | None = None,
          csv_val_1_column: str | None = None, csv_val_2_column: str | None = None, csv_val_3_column: str | None = None, csv_val_4_column: str | None = None,
          csv_val_5_column: str | None = None, csv_val_6_column: str | None = None, csv_val_7_column: str | None = None, csv_val_8_column: str | None = None):
    """
    Generates one query per audio file replacing the #tags# of pattern with the vocals start / end and the given values.

    Parameters
    ----------
    input
        Audio file, directory with audio files or .csv / .xls / .xlsx file with the audio file paths.
    pattern
        Query pattern, tags: #file_name#, #vocals_start_s#, #vocals_start_ms#, #vocals_end_s#, #vocals_end_ms#, #val_N# (alias #csv_val_N#, N = 1..8).
    output
        .sql file to write the queries to.
    base_path
        Folder the relative audio paths in the csv are relative to, by default the paths are used as is.
    csv_file_column
        Name of the csv column with the audio file path, by default the first column.
    recursive
        When input is a directory, also look in its subdirectories.
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
        Value of the #val_1# tag, the default when --csv-val-1-column is not given or its cell is empty.
    val_2
        Value of the #val_2# tag, the default when --csv-val-2-column is not given or its cell is empty.
    val_3
        Value of the #val_3# tag, the default when --csv-val-3-column is not given or its cell is empty.
    val_4
        Value of the #val_4# tag, the default when --csv-val-4-column is not given or its cell is empty.
    val_5
        Value of the #val_5# tag, the default when --csv-val-5-column is not given or its cell is empty.
    val_6
        Value of the #val_6# tag, the default when --csv-val-6-column is not given or its cell is empty.
    val_7
        Value of the #val_7# tag, the default when --csv-val-7-column is not given or its cell is empty.
    val_8
        Value of the #val_8# tag, the default when --csv-val-8-column is not given or its cell is empty.
    csv_val_1_column
        Name of the csv column whose value replaces the #val_1# (or #csv_val_1#) tag.
    csv_val_2_column
        Name of the csv column whose value replaces the #val_2# (or #csv_val_2#) tag.
    csv_val_3_column
        Name of the csv column whose value replaces the #val_3# (or #csv_val_3#) tag.
    csv_val_4_column
        Name of the csv column whose value replaces the #val_4# (or #csv_val_4#) tag.
    csv_val_5_column
        Name of the csv column whose value replaces the #val_5# (or #csv_val_5#) tag.
    csv_val_6_column
        Name of the csv column whose value replaces the #val_6# (or #csv_val_6#) tag.
    csv_val_7_column
        Name of the csv column whose value replaces the #val_7# (or #csv_val_7#) tag.
    csv_val_8_column
        Name of the csv column whose value replaces the #val_8# (or #csv_val_8#) tag.
    """

    console = Console()

    if not silent:
        print_banner(console)

    vals = {n: v for n, v in enumerate((val_1, val_2, val_3, val_4, val_5, val_6, val_7, val_8), start=1) if v is not None}
    csv_columns = {n: c for n, c in enumerate((csv_val_1_column, csv_val_2_column, csv_val_3_column, csv_val_4_column,
                                               csv_val_5_column, csv_val_6_column, csv_val_7_column, csv_val_8_column), start=1) if c is not None}
    is_table = input.suffix.lower() in TABLE_EXTENSIONS

    # every #val_N# / #csv_val_N# tag in the pattern needs its value, from --val-N or --csv-val-N-column
    tags = pattern_tags(pattern)
    missing = [f"--val-{n} / --csv-val-{n}-column" for n in range(1, TAG_COUNT + 1)
               if (f"val_{n}" in tags or f"csv_val_{n}" in tags) and n not in vals and n not in csv_columns]
    if missing:
        print(f"the pattern uses tags without value, missing: {', '.join(missing)}", file=sys.stderr)
        return
    if csv_columns and not is_table:
        print("--csv-val-N-column options require input to be a .csv / .xls / .xlsx file", file=sys.stderr)
        return

    try:
        entries = _ingest(input, recursive, base_path, csv_file_column, vals, csv_columns)
    except Exception as exc:
        print(f"{input}: {exc}", file=sys.stderr)
        return

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("input", str(input)),
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
        print(f"no audio files found in {input}", file=sys.stderr)
        return

    with open(output, "w", encoding="utf-8") as out_file:
        # parameters as sql comment lines
        for key, value in params:
            out_file.write(f"-- {key}: {value}\n")
        out_file.write("\n")

        files = [d.file_path for d in entries]
        cue_options = _cue_options(window, min_db, min_relative_db, min_sustain, min_sustain_interval)
        for i, f, v_s, v_e, _, _ in _analyze_files(console, files, cue_options, silent):
            if v_s == 0 and v_e == 0:
                out_file.write(f"-- {f}: no vocals found\n")
                out_file.flush()
                continue

            # #csv_val_N# is kept as an alias of #val_N#, both take the column value or the --val-N default
            row_vals = {n: getattr(entries[i], f"val_{n}") for n in range(1, TAG_COUNT + 1) if n in vals or n in csv_columns}
            values = {
                **cue_values(v_s, v_e),
                "file_name": f.name,
                **{f"val_{n}": v for n, v in row_vals.items()},
                **{f"csv_val_{n}": v for n, v in row_vals.items()},
            }
            out_file.write(build_query(pattern, values) + "\n")
            out_file.flush()

if __name__ == "__main__":
    app()
