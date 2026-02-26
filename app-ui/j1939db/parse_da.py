"""
Parse J1939 DA Excel (DEC2024 r1) and write j1939.json and spn_db.json to the same directory.

Usage:
    python parse_da.py
    python parse_da.py /path/to/J1939DA.xlsx
"""
import json
import pathlib
import sys

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is required: pip install openpyxl")

_HERE = pathlib.Path(__file__).parent
_DEFAULT_XLSX = _HERE.parent / "j1939da" / "J1939DA DEC2024 r1.xlsx"
_OUTPUT = _HERE / "j1939.json"
_SPN_OUTPUT = _HERE / "spn_db.json"


def _rows(sheet):
    """Yield row tuples (as cell values) starting from row index 4 (0-based)."""
    data = list(sheet.values)
    for row in data[4:]:
        yield row


def parse(xlsx_path: pathlib.Path) -> dict:
    print(f"Opening {xlsx_path} …")
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)

    # ------------------------------------------------------------------ #
    # Industry Groups (B1)
    # col[1]=IG ID (int), col[2]=Description
    # ------------------------------------------------------------------ #
    industry_groups: dict[str, str] = {}
    ws = wb["Industry Groups (B1)"]
    for row in _rows(ws):
        if len(row) < 3 or row[1] is None:
            continue
        try:
            ig_id = int(row[1])
        except (ValueError, TypeError):
            continue
        desc = str(row[2]).strip() if row[2] is not None else ""
        industry_groups[str(ig_id)] = desc
    print(f"  Industry Groups: {len(industry_groups)} entries")

    # ------------------------------------------------------------------ #
    # Manufacturer IDs (B10)
    # col[1]=Mfr ID (int), col[2]=Manufacturer name
    # ------------------------------------------------------------------ #
    manufacturer_codes: dict[str, str] = {}
    ws = wb["Manufacturer IDs (B10)"]
    for row in _rows(ws):
        if len(row) < 3 or row[1] is None:
            continue
        try:
            mfr_id = int(row[1])
        except (ValueError, TypeError):
            continue
        name = str(row[2]).strip() if row[2] is not None else ""
        manufacturer_codes[str(mfr_id)] = name
    print(f"  Manufacturer Codes: {len(manufacturer_codes)} entries")

    # ------------------------------------------------------------------ #
    # Global NAME Functions (B11)
    # col[1]=Function ID (0–127), col[2]=Description
    # ------------------------------------------------------------------ #
    functions_global: dict[str, str] = {}
    ws = wb["Global NAME Functions (B11)"]
    for row in _rows(ws):
        if len(row) < 3 or row[1] is None:
            continue
        try:
            fn_id = int(row[1])
        except (ValueError, TypeError):
            continue
        desc = str(row[2]).strip() if row[2] is not None else ""
        functions_global[str(fn_id)] = desc
    print(f"  Global Functions: {len(functions_global)} entries")

    # ------------------------------------------------------------------ #
    # IG Specific NAME Function (B12)
    # col[1]=IG ID, col[2]=VS ID, col[3]=VS Desc, col[4]=Fn ID, col[5]=Fn Desc
    # ------------------------------------------------------------------ #
    # ig_specific[ig_str]["vehicle_systems"][vs_str] = vs_desc
    # ig_specific[ig_str]["functions"][vs_str][fn_str] = fn_desc
    ig_specific: dict[str, dict] = {}
    ws = wb["IG Specific NAME Function (B12)"]
    for row in _rows(ws):
        if len(row) < 5 or row[1] is None:
            continue
        try:
            ig_id = int(row[1])
            vs_id = int(row[2]) if row[2] is not None else None
        except (ValueError, TypeError):
            continue
        if vs_id is None:
            continue

        vs_desc = str(row[3]).strip() if row[3] is not None else ""

        ig_str = str(ig_id)
        vs_str = str(vs_id)

        if ig_str not in ig_specific:
            ig_specific[ig_str] = {"vehicle_systems": {}, "functions": {}}

        ig_specific[ig_str]["vehicle_systems"][vs_str] = vs_desc

        # Function may be absent for VS-only rows
        if len(row) >= 6 and row[4] is not None:
            try:
                fn_id = int(row[4])
            except (ValueError, TypeError):
                continue
            fn_desc = str(row[5]).strip() if row[5] is not None else ""
            fn_str = str(fn_id)

            if vs_str not in ig_specific[ig_str]["functions"]:
                ig_specific[ig_str]["functions"][vs_str] = {}
            ig_specific[ig_str]["functions"][vs_str][fn_str] = fn_desc

    ig_count = sum(
        sum(len(fns) for fns in ig["functions"].values())
        for ig in ig_specific.values()
    )
    print(f"  IG-Specific Functions: {ig_count} entries across {len(ig_specific)} industry groups")

    # ------------------------------------------------------------------ #
    # SPs & PGs — SPN definitions
    # Header is at row index 3 (0-based), data starts at row 4.
    # Column indices verified from the DEC2024 r1 header row:
    #   4  = PGN (int or string)
    #   5  = PG Label
    #   6  = PG Acronym
    #   18 = SP Start Bit  (string e.g. "4.1" = byte 4 bit 1, 1-indexed)
    #   19 = SPN number    (int)
    #   20 = SP Label
    #   22 = SP Length     (string e.g. "1 byte", "2 bits")
    #   27 = Unit
    #   32 = Scale Factor  (numeric only column)
    #   33 = Offset        (numeric only column) — equals spec minimum physical value
    #   34 = Range Maximum (numeric only column) — spec maximum physical value
    # ------------------------------------------------------------------ #
    spn_db: dict[str, dict] = {}

    def _parse_start_bit(s) -> int | None:
        """Convert J1939 'byte.bit' notation to 0-based bit offset."""
        try:
            parts = str(s).strip().split('.')
            byte_num = int(float(parts[0]))
            bit_num = int(parts[1]) if len(parts) > 1 else 1
            return (byte_num - 1) * 8 + (bit_num - 1)
        except (ValueError, AttributeError):
            return None

    def _parse_length(s) -> int | None:
        """Convert length string to number of bits."""
        if s is None:
            return None
        s = str(s).strip().lower()
        if 'byte' in s:
            try:
                n = int(float(s.split()[0]))
                return n * 8
            except (ValueError, IndexError):
                return None
        elif 'bit' in s:
            try:
                return int(float(s.split()[0]))
            except (ValueError, IndexError):
                return None
        try:
            return int(float(s))
        except ValueError:
            return None

    try:
        ws_spg = wb["SPs & PGs"]
    except KeyError:
        print("  WARNING: 'SPs & PGs' sheet not found — skipping SPN extraction")
        ws_spg = None

    if ws_spg is not None:
        spn_rows = 0
        skipped = 0
        data = list(ws_spg.values)
        for row in data[4:]:
            if len(row) < 35:
                continue
            pgn_raw = row[4]
            pg_label = row[5]
            pg_acronym = row[6]
            start_bit_raw = row[18]
            spn_raw = row[19]
            sp_label = row[20]
            sp_length_raw = row[22]
            unit_raw = row[27]
            scale_raw = row[32]
            offset_raw = row[33]
            range_max_raw = row[34]

            # Must have PGN and SPN
            if pgn_raw is None or spn_raw is None:
                continue

            # Parse numerics
            try:
                pgn = int(pgn_raw)
                spn = int(spn_raw)
            except (ValueError, TypeError):
                continue

            # Parse scale and offset — must be real numbers
            try:
                scale = float(scale_raw)
                offset = float(offset_raw)
            except (ValueError, TypeError):
                skipped += 1
                continue

            # Unit must be non-empty
            unit = str(unit_raw).strip() if unit_raw is not None else ''
            if not unit:
                skipped += 1
                continue

            # Parse start bit
            bit_offset = _parse_start_bit(start_bit_raw)
            if bit_offset is None:
                skipped += 1
                continue

            # Parse length
            length = _parse_length(sp_length_raw)
            if length is None or length <= 0:
                skipped += 1
                continue

            pgn_str = str(pgn)
            if pgn_str not in spn_db:
                spn_db[pgn_str] = {
                    "label": str(pg_label).strip() if pg_label is not None else '',
                    "acronym": str(pg_acronym).strip() if pg_acronym is not None else '',
                    "spns": [],
                }

            # Parse range maximum (optional — not all SPNs have a numeric max)
            range_max: float | None = None
            try:
                range_max = float(range_max_raw)
            except (ValueError, TypeError):
                pass

            spn_db[pgn_str]["spns"].append({
                "spn": spn,
                "label": str(sp_label).strip() if sp_label is not None else f"SPN {spn}",
                "bit_offset": bit_offset,
                "length": length,
                "scale": scale,
                "offset": offset,
                "unit": unit,
                "range_max": range_max,
            })
            spn_rows += 1

        print(f"  SPN DB: {spn_rows} SPNs across {len(spn_db)} PGNs  (skipped {skipped} rows)")

    wb.close()

    return {
        "industry_groups": industry_groups,
        "manufacturer_codes": manufacturer_codes,
        "functions_global": functions_global,
        "ig_specific": ig_specific,
    }, spn_db


def main() -> None:
    xlsx_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_XLSX
    if not xlsx_path.exists():
        sys.exit(f"Excel file not found: {xlsx_path}")

    db, spn_db = parse(xlsx_path)

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(db, indent=2, ensure_ascii=False))
    print(f"\nWrote {_OUTPUT}  ({_OUTPUT.stat().st_size:,} bytes)")

    _SPN_OUTPUT.write_text(json.dumps(spn_db, indent=2, ensure_ascii=False))
    print(f"Wrote {_SPN_OUTPUT}  ({_SPN_OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
