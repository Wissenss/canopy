import csv
import sys
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg"}
CSV_EXTENSIONS = {".csv"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}
VAL_COUNT = 8

class Data:
    def __init__(self) -> None:
        self.file_path : Path = Path()
        self.val_1 : str = ""
        self.val_2 : str = ""
        self.val_3 : str = ""
        self.val_4 : str = ""
        self.val_5 : str = ""
        self.val_6 : str = ""
        self.val_7 : str = ""
        self.val_8 : str = ""

        # this values are expected to be filled by processing the files

        self.v_p : bool = False # weather or not this files was processed for vocals
        self.v_s : float = 0
        self.v_e : float = 0
        self.processing_time : float = 0 # seconds the processing took
        self.finished_at : str = "" # when the processing finished, as "%Y-%m-%d %H:%M:%S"

    def __repr__(self) -> str:
        vals = ", ".join(f"val_{n}={getattr(self, f'val_{n}')!r}" for n in range(1, VAL_COUNT + 1) if getattr(self, f"val_{n}"))
        return f"Data({str(self.file_path)!r}{', ' + vals if vals else ''})"

class DataIngestor:
    def __init__(self) -> None:
        self.path : Path = Path()
        self.recursive : bool = False # if path is directory weather or not to look for files in subdirectories
        self.base_path : Path | None = None # if path is a csv or excel file, the folder relative audio paths are resolved from, None = paths used as is
        self.val_1 : str = "" # the value to set for val_1 if no other source provides it
        self.val_2 : str = ""
        self.val_3 : str = ""
        self.val_4 : str = ""
        self.val_5 : str = ""
        self.val_6 : str = ""
        self.val_7 : str = ""
        self.val_8 : str = ""
        self.tbl_start_row : int = 1 # if path is a csv or excel file, the 1-based row reading starts at (the header row when column names are used)
        self.tbl_col_name_file_path : str = "" # if path is a csv or excel file, the name of the header column with the audio file path, "" = first column
        self.tbl_col_name_val_1 : str = "" # if path is a csv or excel file, the name of the header column that val_1 will take its value from (todo: support column index)
        self.tbl_col_name_val_2 : str = ""
        self.tbl_col_name_val_3 : str = ""
        self.tbl_col_name_val_4 : str = ""
        self.tbl_col_name_val_5 : str = ""
        self.tbl_col_name_val_6 : str = ""
        self.tbl_col_name_val_7 : str = ""
        self.tbl_col_name_val_8 : str = ""

    def ingest(self) -> list[Data]:
        if self.path.is_dir():
            return self._ingest_directory()

        suffix = self.path.suffix.lower()

        if suffix in AUDIO_EXTENSIONS:
            return self._ingest_audio_file()

        if suffix in CSV_EXTENSIONS:
            return self._ingest_csv_file()

        if suffix in EXCEL_EXTENSIONS:
            return self._ingest_excel_file()

        raise ValueError(f"the specified path is not supported: {self.path}")

    def _new_data(self, file_path: Path, values: dict[int, str] | None = None) -> Data:
        """
            returns a Data for file_path, each val_N takes values[N] when given and not empty, the ingestor's val_N otherwise.
        """

        if values is None:
            values = {}

        data = Data()
        data.file_path = file_path
        for n in range(1, VAL_COUNT + 1):
            setattr(data, f"val_{n}", values.get(n) or getattr(self, f"val_{n}"))
        return data

    def _ingest_audio_file(self) -> list[Data]:
        return [self._new_data(self.path)]

    def _ingest_csv_file(self) -> list[Data]:
        # csv files saved by excel on spanish windows are usually cp1252, not utf-8
        try:
            with open(self.path, newline="", encoding="utf-8-sig") as file:
                rows = list(csv.reader(file))
        except UnicodeDecodeError:
            with open(self.path, newline="", encoding="cp1252") as file:
                rows = list(csv.reader(file))

        return self._ingest_rows(rows)

    def _ingest_excel_file(self) -> list[Data]:
        rows = []

        if self.path.suffix.lower() == ".xls":
            import xlrd
            sheet = xlrd.open_workbook(str(self.path)).sheet_by_index(0)
            for r in range(sheet.nrows):
                rows.append([_cell_to_str(v) for v in sheet.row_values(r)])
        else:
            import openpyxl
            workbook = openpyxl.load_workbook(str(self.path), read_only=True, data_only=True)
            try:
                for row in workbook.worksheets[0].iter_rows(values_only=True):
                    rows.append([_cell_to_str(v) for v in row])
            finally:
                workbook.close()

        return self._ingest_rows(rows)

    def _ingest_directory(self) -> list[Data]:
        pattern = "**/*" if self.recursive else "*"
        files = sorted(f for f in self.path.glob(pattern) if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
        return [self._new_data(f) for f in files]

    def _ingest_rows(self, rows: list[list[str]]) -> list[Data]:
        """
            returns a Data per table row, starting at tbl_start_row.

            without column names the first column is the file and the header row is optional (skipped when its first cell is not an audio file);
            with column names (tbl_col_name_*) the first row read must be the header, an empty tbl_col_name_file_path falls back to the first column.
            blank lines and '#' lines are skipped; relative audio paths are resolved from base_path, if given.
        """

        value_columns = {n: getattr(self, f"tbl_col_name_val_{n}") for n in range(1, VAL_COUNT + 1) if getattr(self, f"tbl_col_name_val_{n}")}
        use_header = bool(self.tbl_col_name_file_path) or bool(value_columns)
        file_idx = 0
        value_idx = {}
        header_read = False

        data = []
        for line_no, row in enumerate(rows, start=1):
            if line_no < self.tbl_start_row:
                continue

            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue

            if not header_read:
                header_read = True
                if use_header:
                    if self.tbl_col_name_file_path:
                        file_idx = _find_column(row, self.tbl_col_name_file_path)
                    value_idx = {n: _find_column(row, name) for n, name in value_columns.items()}
                    continue
                if Path(row[0].strip()).suffix.lower() not in AUDIO_EXTENSIONS:
                    continue

            if len(row) <= max([file_idx, *value_idx.values()]):
                print(f"{self.path}:{line_no}: missing columns, skipped", file=sys.stderr)
                continue

            audio_path = Path(row[file_idx].strip())
            if self.base_path is not None and not audio_path.is_absolute():
                audio_path = self.base_path / audio_path

            data.append(self._new_data(audio_path, {n: row[idx].strip() for n, idx in value_idx.items()}))

        return data

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

if __name__ == "__main__":
    ingestor = DataIngestor()

    # to test a directory path
    #ingestor.path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./other/sandbox/audios/short")
    #ingestor.val_1 = "default"
    
    # to test an xls file path
    ingestor.path = Path(r"C:\dev\random\canopy\other\rolas.xls")
    ingestor.tbl_col_name_file_path = "Archivo"
    ingestor.tbl_col_name_val_1 = "CartuchoId"
    ingestor.tbl_col_name_val_2 = "IdMedia"

    for d in ingestor.ingest():
        print(d)
