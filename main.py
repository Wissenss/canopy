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
from query_builder import seconds_to_ms, build_cue_update

app = App(name="canopy", version=__version__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg"}

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

def _analyze_files(console: Console, files: list[Path], window: int, min_db: float, silent: bool):
    """
        runs get_vocal_cues on each file showing the progress and a results table.

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
                v_s, v_e = get_vocal_cues(str(f), window, min_db)
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
def vocal_cues(file_path: Path, output: Path | None = None, window: int = 60, min_db: float = -40, recursive: bool = False, silent: bool = False):
    """
        prints the second when the voice starts / ends in the given audio file(s).

        parms:
            file_path : audio file to analyze, or a directory with audio files
            output : optional .csv or .txt file to store the results
            window : seconds analyzed at the start / end of each file
            min_db : vocals level (dBFS) considered voice
            recursive : when file_path is a directory, also look in its subdirectories
            silent : disables the progress indicators
    """

    console = Console()

    if not silent:
        print_banner(console)

    if file_path.is_dir():
        pattern = "**/*" if recursive else "*"
        files = sorted(f for f in file_path.glob(pattern) if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
    else:
        files = [file_path]

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("file_path", str(file_path)),
        ("files", str(len(files))),
        ("output", str(output) if output is not None else "-"),
        ("window", f"{window} s"),
        ("min_db", f"{min_db} dBFS"),
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
        for _, f, v_s, v_e, elapsed, finished_at in _analyze_files(console, files, window, min_db, silent):
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

def _read_cartuchos_csv(csv_path: Path, base_path: Path | None = None, file_column: str | None = None, id_column: str | None = None) -> list[tuple[Path, int]]:
    """
        reads the (audio file, CartuchoId) pairs from csv_path.

        without column names the first column is the file and the second one the CartuchoId, the header row is optional;
        with column names (file_column / id_column) the first row must be the header, a missing name falls back to its default position.
        blank lines and '#' lines are skipped; relative audio paths are resolved from base_path (defaults to the csv folder).
    """

    if base_path is None:
        base_path = csv_path.parent

    use_header = file_column is not None or id_column is not None
    file_idx, id_idx = 0, 1
    header_read = False

    entries = []
    for line_no, row in enumerate(_read_rows(csv_path), start=1):
        if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
            continue

        if use_header and not header_read:
            header_read = True
            if file_column is not None:
                file_idx = _find_column(row, file_column)
            if id_column is not None:
                id_idx = _find_column(row, id_column)
            continue

        if len(row) <= max(file_idx, id_idx):
            print(f"{csv_path}:{line_no}: missing columns, skipped", file=sys.stderr)
            continue

        try:
            cartucho_id = int(row[id_idx].strip())
        except ValueError:
            # header row (only when no column names were given)
            if not use_header and not header_read:
                header_read = True
                continue
            print(f"{csv_path}:{line_no}: invalid CartuchoId '{row[id_idx]}', skipped", file=sys.stderr)
            continue

        header_read = True

        audio_path = Path(row[file_idx].strip())
        if not audio_path.is_absolute():
            audio_path = base_path / audio_path

        entries.append((audio_path, cartucho_id))

    return entries

@app.command
def tsaq(csv_path: Path, output: Path | None = None, base_path: Path | None = None, file_column: str | None = None, id_column: str | None = None, start_offset: float = 0,
         end_offset: float = 0, content_type: int = 3, window: int = 60, min_db: float = -40, silent: bool = False):
    """
        produces a .sql file that updates the CARTUCHOS vocals start / end (TiempoEntrada / TiempoSalida) of the audio files listed in a csv.

        parms:
            csv_path : .csv, .xls or .xlsx file with the audio file path in the first column and the CartuchoId in the second one
            output : .sql file to write, defaults to csv_path with the .sql extension
            base_path : folder the relative audio paths in the csv are relative to, defaults to the csv folder
            file_column : name of the csv column with the audio file path, defaults to the first column
            id_column : name of the csv column with the CartuchoId, defaults to the second column
            start_offset : seconds added to the vocals start (can be negative)
            end_offset : seconds added to the vocals end (can be negative)
            content_type : TipoContenido used in the WHERE clause
            window : seconds analyzed at the start / end of each file
            min_db : vocals level (dBFS) considered voice
            silent : disables the progress indicators
    """

    console = Console()

    if not silent:
        print_banner(console)

    if output is None:
        output = csv_path.with_suffix(".sql")

    try:
        entries = _read_cartuchos_csv(csv_path, base_path, file_column, id_column)
    except Exception as exc:
        print(f"{csv_path}: {exc}", file=sys.stderr)
        return

    params = [
        ("version", __version__),
        ("started_at", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        ("csv_path", str(csv_path)),
        ("base_path", str(base_path) if base_path is not None else f"{csv_path.parent} (csv folder)"),
        ("file_column", file_column if file_column is not None else "1st column"),
        ("id_column", id_column if id_column is not None else "2nd column"),
        ("files", str(len(entries))),
        ("output", str(output)),
        ("start_offset", f"{start_offset} s"),
        ("end_offset", f"{end_offset} s"),
        ("content_type", str(content_type)),
        ("window", f"{window} s"),
        ("min_db", f"{min_db} dBFS"),
        ("silent", str(silent)),
    ]
    _print_params(console, params)

    if not entries:
        print(f"no audio files found in {csv_path}", file=sys.stderr)
        return

    import librosa

    with open(output, "w", encoding="utf-8") as out_file:
        for key, value in params:
            out_file.write(f"-- {key}: {value}\n")
        out_file.write("\n")

        files = [audio_path for audio_path, _ in entries]
        for i, f, v_s, v_e, _, _ in _analyze_files(console, files, window, min_db, silent):
            cartucho_id = entries[i][1]

            if v_s == 0 and v_e == 0:
                out_file.write(f"-- CartuchoId {cartucho_id} ({f}): no vocals found\n")
                out_file.flush()
                continue

            # offsets are applied in seconds, then the times are kept inside the file
            duration = librosa.get_duration(path=str(f))
            start = min(max(0.0, v_s + start_offset), duration)
            end = min(max(start, v_e + end_offset), duration)

            out_file.write(build_cue_update(cartucho_id, seconds_to_ms(start), seconds_to_ms(end), content_type) + "\n")
            out_file.flush()

if __name__ == "__main__":
    app()
