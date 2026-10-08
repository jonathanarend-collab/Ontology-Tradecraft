#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import datetime as _dt

import pandas as pd
from dateutil import parser as dateparser


# ============================================================
# PATHS RESOLVED RELATIVE TO THIS SCRIPT
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent          # .../src/scripts
SRC_DIR = SCRIPT_DIR.parent                          # .../src
DATA_DIR = SRC_DIR / "data"                          # .../src/data

IN_A = Path("src/data/sensor_A.csv")
IN_B = Path("src/data/sensor_B.json")
IN_C = Path("src/data/sensor_C.csv")
OUT  = Path("src/data/readings_normalized.csv")


# ============================================================
# CANONICAL OUTPUT COLUMNS
# ============================================================

CANON = [
    "artifact_id",
    "sdc_kind",
    "unit_label",
    "value",
    "timestamp",
]


# ============================================================
# HELPERS
# ============================================================

def _to_iso_utc(x: Any) -> str | None:
    """
    Parse any timestamp to ISO-8601 in UTC with 'Z'.

    If a timestamp has no timezone information, this function
    assumes UTC.
    """

    if x is None:
        return None

    s = str(x).strip()

    if not s or s.lower() in {"nan", "none"}:
        return None

    try:
        dt = dateparser.parse(s)

        if dt is None:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)

        return (
            dt.astimezone(_dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    except Exception:
        return None


def _to_float(x: Any) -> float | None:
    """
    Convert a value to float.

    Invalid or blank values return None so they can later
    be removed from the normalized dataset.
    """

    if x is None:
        return None

    s = str(x).strip()

    if s == "" or s.lower() in {"nan", "none"}:
        return None

    try:
        return float(s)

    except Exception:
        return None


def _norm_artifact_id(x: Any) -> str | None:
    """
    Normalize artifact/device identifiers.

    Sensor A uses 'Chiller 3' while Sensor B uses 'Chiller-3'.
    These represent the same artifact, so both are normalized
    to the same canonical identifier.
    """

    if x is None:
        return None

    s = str(x).strip()

    if not s:
        return None

    aliases = {
        "chiller 3": "Chiller-3",
        "chiller-3": "Chiller-3",
    }

    return aliases.get(s.lower(), s)


def _norm_kind(k: Any) -> str | None:
    """
    Normalize reading type/kind labels.
    """

    if k is None:
        return None

    s = str(k).strip()

    if not s:
        return None

    low = s.lower()

    if low in {"temp", "temperature"}:
        return "temperature"

    if low == "pressure":
        return "pressure"

    if low == "voltage":
        return "voltage"

    if low == "resistance":
        return "resistance"

    # Fallback for an unexpected measurement kind.
    return s


def _norm_unit(u: Any) -> str | None:
    """
    Normalize spelling and abbreviations of unit labels.

    Numeric unit conversion happens later.
    """

    if u is None:
        return None

    s = str(u).strip()

    if not s:
        return None

    low = s.lower()

    # -------------------------
    # Temperature
    # -------------------------

    if low in {"celsius", "°c", "c"}:
        return "C"

    if low in {"fahrenheit", "°f", "f"}:
        return "F"

    # -------------------------
    # Pressure
    # -------------------------

    if low == "psi":
        return "psi"

    if low in {
        "kpa",
        "kilopascal",
        "kilopascals",
    }:
        return "kPa"

    # -------------------------
    # Electrical
    # -------------------------

    if low in {
        "v",
        "volt",
        "volts",
    }:
        return "V"

    if low in {
        "ohm",
        "ohms",
        "Ω",
        "ω",
    }:
        return "ohm"

    # Pass through unexpected units.
    return s


# ============================================================
# LOAD SENSOR A
# ============================================================

def load_sensor_a(path: Path) -> pd.DataFrame:
    """
    Sensor A CSV columns:

    Device Name
    Reading Type
    Reading Value
    Units
    Time (Local)

    Maps them to the canonical Project 4 columns.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}"
        )

    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
    )

    rename_map = {
        "Device Name": "artifact_id",
        "Reading Type": "sdc_kind",
        "Reading Value": "value",
        "Units": "unit_label",
        "Time (Local)": "timestamp",
    }

    # Remove accidental whitespace from column names.
    fixed_cols = {
        c: c.strip()
        for c in df.columns
    }

    df = df.rename(
        columns=fixed_cols
    )

    df = df.rename(
        columns={
            k: v
            for k, v in rename_map.items()
            if k in df.columns
        }
    )

    # Ensure every canonical column exists.
    for c in CANON:
        if c not in df.columns:
            df[c] = None

    return df[CANON].copy()


# ============================================================
# LOAD SENSOR B
# ============================================================

def load_sensor_b(path: Path) -> pd.DataFrame:
    """
    Flatten the nested Sensor B JSON structure into the
    canonical Project 4 columns.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}"
        )

    obj = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    readings = (
        obj.get("readings", [])
        if isinstance(obj, dict)
        else []
    )

    rows: List[Dict[str, Any]] = []

    for entry in readings:

        entity = entry.get(
            "entity_id"
        )

        for d in entry.get(
            "data",
            [],
        ) or []:

            rows.append(
                {
                    "artifact_id": entity,
                    "sdc_kind": d.get("kind"),
                    "unit_label": d.get("unit"),
                    "value": d.get("value"),
                    "timestamp": d.get("time"),
                }
            )

    return pd.DataFrame(
        rows,
        columns=CANON,
    )


# ============================================================
# NORMALIZATION AND CLEANING
# ============================================================

def normalize_and_clean(
    df: pd.DataFrame
) -> pd.DataFrame:

    # --------------------------------------------------------
    # 1. Trim whitespace from string fields.
    # --------------------------------------------------------

    for col in [
        "artifact_id",
        "sdc_kind",
        "unit_label",
        "timestamp",
    ]:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
        )


    # --------------------------------------------------------
    # 2. Normalize artifact identifiers.
    #
    # Chiller 3 -> Chiller-3
    # --------------------------------------------------------

    df["artifact_id"] = (
        df["artifact_id"]
        .apply(_norm_artifact_id)
    )


    # --------------------------------------------------------
    # 3. Normalize measurement kind labels.
    #
    # temp -> temperature
    # Temperature -> temperature
    # --------------------------------------------------------

    df["sdc_kind"] = (
        df["sdc_kind"]
        .apply(_norm_kind)
    )


    # --------------------------------------------------------
    # 4. Normalize unit spellings.
    #
    # volt -> V
    # Celsius -> C
    # etc.
    # --------------------------------------------------------

    df["unit_label"] = (
        df["unit_label"]
        .apply(_norm_unit)
    )


    # --------------------------------------------------------
    # 5. Convert values to numeric.
    #
    # Invalid values such as "not_a_number" become None.
    # --------------------------------------------------------

    df["value"] = (
        df["value"]
        .apply(_to_float)
    )


    # --------------------------------------------------------
    # 6. Convert timestamps to ISO-8601.
    # --------------------------------------------------------

    df["timestamp"] = (
        df["timestamp"]
        .apply(_to_iso_utc)
    )


    # ========================================================
    # 7. CONVERT TEMPERATURE TO CELSIUS
    # ========================================================
    #
    # Canonical temperature unit:
    #
    #     C
    #
    # Formula:
    #
    #     C = (F - 32) * 5 / 9
    #
    # Examples:
    #
    #     212 F -> 100 C
    #      68 F -> 20 C
    # ========================================================

    fahrenheit_mask = (
        (df["sdc_kind"] == "temperature")
        & (df["unit_label"] == "F")
        & (df["value"].notna())
    )

    df.loc[
        fahrenheit_mask,
        "value"
    ] = (
        (
            df.loc[
                fahrenheit_mask,
                "value"
            ]
            - 32
        )
        * 5
        / 9
    )

    df.loc[
        fahrenheit_mask,
        "unit_label"
    ] = "C"


    # ========================================================
    # 8. CONVERT PRESSURE TO KILOPASCALS
    # ========================================================
    #
    # Canonical pressure unit:
    #
    #     kPa
    #
    # Conversion:
    #
    #     1 psi = 6.894757293168 kPa
    #
    # Example:
    #
    #     14.7 psi -> approximately 101.353 kPa
    # ========================================================

    psi_mask = (
        (df["sdc_kind"] == "pressure")
        & (df["unit_label"] == "psi")
        & (df["value"].notna())
    )

    df.loc[
        psi_mask,
        "value"
    ] = (
        df.loc[
            psi_mask,
            "value"
        ]
        * 6.894757293168
    )

    df.loc[
        psi_mask,
        "unit_label"
    ] = "kPa"


    # --------------------------------------------------------
    # 9. Round converted numeric values.
    #
    # This prevents unnecessarily long floating-point values
    # such as 101.3529322095696.
    # --------------------------------------------------------

    df["value"] = (
        df["value"]
        .round(6)
    )


    # --------------------------------------------------------
    # 10. Diagnostics before dropping invalid rows.
    # --------------------------------------------------------

    total = len(df)

    missing_counts = {
        "artifact_id": int(
            df["artifact_id"].isna().sum()
            + (df["artifact_id"] == "").sum()
        ),

        "sdc_kind": int(
            df["sdc_kind"].isna().sum()
            + (df["sdc_kind"] == "").sum()
        ),

        "unit_label": int(
            df["unit_label"].isna().sum()
            + (df["unit_label"] == "").sum()
        ),

        "value": int(
            df["value"].isna().sum()
        ),

        "timestamp": int(
            df["timestamp"].isna().sum()
        ),
    }

    print(
        "[diagnostics] total rows:",
        total,
        "| missing:",
        missing_counts,
    )


    # --------------------------------------------------------
    # 11. Replace blank strings with NA.
    # --------------------------------------------------------

    df = df.replace(
        {"": pd.NA}
    )


    # --------------------------------------------------------
    # 12. Drop rows missing any critical value.
    #
    # This removes:
    #
    # Sensor A:
    #   not_a_number
    #   blank pressure value
    #
    # Sensor B:
    #   null temperature value
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "artifact_id",
            "sdc_kind",
            "unit_label",
            "value",
            "timestamp",
        ]
    )


    # ========================================================
    # 13. VERIFY UNIT CONSISTENCY
    # ========================================================
    #
    # These are the canonical units expected after conversion.
    # ========================================================

    expected_units = {
        "temperature": "C",
        "pressure": "kPa",
        "voltage": "V",
        "resistance": "ohm",
    }

    for kind, expected_unit in expected_units.items():

        observed_units = set(
            df.loc[
                df["sdc_kind"] == kind,
                "unit_label"
            ]
            .dropna()
            .unique()
        )

        if observed_units and observed_units != {expected_unit}:

            raise ValueError(
                f"Inconsistent units for {kind}. "
                f"Expected only '{expected_unit}', "
                f"but found {sorted(observed_units)}"
            )


    # --------------------------------------------------------
    # 14. Sort deterministically.
    # --------------------------------------------------------

    df = (
        df.sort_values(
            [
                "artifact_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )


    # --------------------------------------------------------
    # 15. Put columns in exact canonical order.
    # --------------------------------------------------------

    df = df[CANON]

    return df


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[paths] A:",
        IN_A
    )

    print(
        "[paths] B:",
        IN_B
    )

   print(
        "[paths] C:",
        IN_C
    )


    # --------------------------------------------------------
    # Load both raw sources.
    # --------------------------------------------------------

    df_a = load_sensor_a(
        IN_A
    )

    df_b = load_sensor_b(
        IN_B
    )
    df_c = load_sensor_a(
        IN_C
    )


    print(
        f"[normalize_readings] "
        f"Input A rows: {len(df_a)}"
    )

    print(
        f"[normalize_readings] "
        f"Input B rows: {len(df_b)}"
    )
  print(
        f"[normalize_readings] "
        f"Input C rows: {len(df_c)}"
    )


    # --------------------------------------------------------
    # Combine both sources.
    # --------------------------------------------------------

    combined = pd.concat(
        [
            df_a,
            df_b,
            df_c
        ],
        ignore_index=True,
    )


    # --------------------------------------------------------
    # Normalize and clean the combined data.
    # --------------------------------------------------------

    cleaned = normalize_and_clean(
        combined
    )


    # --------------------------------------------------------
    # Create output directory if necessary.
    # --------------------------------------------------------

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Save canonical normalized CSV.
    # --------------------------------------------------------

    cleaned.to_csv(
        OUT,
        index=False,
    )


    # --------------------------------------------------------
    # Report results.
    # --------------------------------------------------------

    print(
        f"[normalize_readings] "
        f"Output rows : {len(cleaned)}"
    )

    print(
        f"[normalize_readings] "
        f"Wrote       : {OUT}"
    )


    # --------------------------------------------------------
    # Show unit consistency.
    # --------------------------------------------------------

    print(
        "\n[normalize_readings] "
        "Canonical units:"
    )

    for kind in sorted(
        cleaned["sdc_kind"].unique()
    ):

        units = sorted(
            cleaned.loc[
                cleaned["sdc_kind"] == kind,
                "unit_label"
            ].unique()
        )

        print(
            f"  {kind}: {', '.join(units)}"
        )


# ============================================================
# RUN SCRIPT
# ============================================================

if __name__ == "__main__":
    main()
