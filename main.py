import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from cyclopts import App
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn

app = App()

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg"}

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

    if file_path.is_dir():
        pattern = "**/*" if recursive else "*"
        files = sorted(f for f in file_path.glob(pattern) if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
    else:
        files = [file_path]

    if not files:
        print(f"no audio files found in {file_path}", file=sys.stderr)
        return

    out_file = None
    writer = None
    if output is not None:
        out_file = open(output, "w", newline="", encoding="utf-8")
        if output.suffix.lower() == ".csv":
            writer = csv.writer(out_file)
            writer.writerow(["file", "vocals_start", "vocals_end", "processing_time", "finished_at"])

    columns = (TextColumn("{task.description}"), BarColumn(complete_style="blue", finished_style="blue", pulse_style="blue"), MofNCompleteColumn(), TimeElapsedColumn())

    try:
        with Progress(*columns, disable=silent) as progress:
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
            for f in files:
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
                finished_at = f"[{datetime.now():%Y-%m-%d %H:%M:%S}]"

                row = row_table()
                row.add_row(finished_at, str(f), f"{v_s:.3f}", f"{v_e:.3f}", f"{elapsed:.2f}")
                progress.console.print(row)

                if writer is not None:
                    writer.writerow([str(f), f"{v_s:.3f}", f"{v_e:.3f}", f"{elapsed:.2f}", finished_at])
                elif out_file is not None:
                    out_file.write(f"file: {f}\nvocals_start: {v_s:.3f}\nvocals_end: {v_e:.3f}\nprocessing_time: {elapsed:.2f}\nfinished_at: {finished_at}\n\n")

                if out_file is not None:
                    out_file.flush()

            progress.update(files_task, description="done")
    finally:
        if out_file is not None:
            out_file.close()

if __name__ == "__main__":
    app()
