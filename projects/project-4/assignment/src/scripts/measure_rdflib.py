from pathlib import Path
from decimal import Decimal

import pandas as pd
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import RDF, RDFS, XSD, OWL


# ============================================================
# FILE PATHS
# ============================================================

# This file should live at:
# assignment/src/scripts/measure_rdflib.py
#
# parents[1] therefore points to:
# assignment/src/

SRC_DIR = Path(__file__).resolve().parents[1]

DATA_FILE = SRC_DIR / "data" / "readings_normalized.csv"
OUTPUT_FILE = SRC_DIR / "measure_cco.ttl"


# ============================================================
# NAMESPACES
# ============================================================

# These namespaces match the CCO/BFO namespaces used by the
# supplied Project 4 materials.

BFO = Namespace(
    "http://purl.obolibrary.org/obo/bfo.owl#"
)

CCO = Namespace(
    "http://www.ontologyrepository.com/CommonCoreOntologies/"
)

EX = Namespace(
    "http://example.org/project4/"
)


# ============================================================
# CCO CLASSES AND PROPERTIES
# ============================================================

# Measurement Information Content Entity
MICE_CLASS = CCO.MeasurementInformationContentEntity

# Measurement Unit
MEASUREMENT_UNIT_CLASS = CCO.MeasurementUnit

# MICE -> SDC
IS_MEASURE_OF = CCO.is_a_measurement_of

# MICE -> numeric literal
HAS_VALUE = CCO.has_decimal_value

# MICE -> Measurement Unit
USES_MEASUREMENT_UNIT = CCO.uses_measurement_unit


# ============================================================
# REQUIRED CSV COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "artifact_id",
    "sdc_kind",
    "unit_label",
    "value",
    "timestamp",
]


# ============================================================
# HELPER FUNCTION
# ============================================================

def safe_id(value):
    """
    Convert a CSV value into a string that is safer to use
    inside one of our locally generated IRIs.
    """

    return (
        str(value)
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():

    # --------------------------------------------------------
    # 1. Verify the normalized CSV exists.
    # --------------------------------------------------------

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Could not find normalized readings file:\n"
            f"{DATA_FILE}"
        )


    # --------------------------------------------------------
    # 2. Load the normalized CSV.
    # --------------------------------------------------------

    df = pd.read_csv(DATA_FILE)

    print(f"Loaded {len(df)} normalized measurement rows.")


    # --------------------------------------------------------
    # 3. Verify all required columns exist.
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "The normalized CSV is missing required columns: "
            + ", ".join(missing_columns)
        )


    # --------------------------------------------------------
    # 4. Create the RDF graph.
    # --------------------------------------------------------

    g = Graph()


    # --------------------------------------------------------
    # 5. Bind namespaces.
    # --------------------------------------------------------

    g.bind("bfo", BFO)
    g.bind("cco", CCO)
    g.bind("ex", EX)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("owl", OWL)


    # --------------------------------------------------------
    # 6. Add basic ontology metadata.
    # --------------------------------------------------------

    ontology = EX.Project4MeasurementOntology

    g.add(
        (
            ontology,
            RDF.type,
            OWL.Ontology
        )
    )

    g.add(
        (
            ontology,
            RDFS.label,
            Literal(
                "Project 4 Measurement Ontology",
                lang="en"
            )
        )
    )


    # --------------------------------------------------------
    # 7. Process each normalized measurement row.
    # --------------------------------------------------------

    for index, row in df.iterrows():

        # ----------------------------------------------------
        # Read values from the normalized CSV.
        # ----------------------------------------------------

        artifact_id = str(
            row["artifact_id"]
        ).strip()

        sdc_kind = str(
            row["sdc_kind"]
        ).strip()

        unit_label = str(
            row["unit_label"]
        ).strip()

        timestamp = str(
            row["timestamp"]
        ).strip()

        # Decimal is used instead of float so that the RDF
        # literal can cleanly use xsd:decimal.
        value = Decimal(
            str(row["value"])
        )


        # ----------------------------------------------------
        # Build safe identifiers.
        # ----------------------------------------------------

        artifact_key = safe_id(
            artifact_id
        )

        sdc_key = safe_id(
            sdc_kind
        )

        unit_key = safe_id(
            unit_label
        )


        # ----------------------------------------------------
        # Create RDF individuals.
        # ----------------------------------------------------

        # Physical artifact being measured
        artifact = EX[
            f"artifact_{artifact_key}"
        ]

        # Specifically Dependent Continuant associated
        # with that artifact, such as temperature or pressure
        sdc = EX[
            f"sdc_{artifact_key}_{sdc_key}"
        ]

        # Each normalized reading gets its own MICE
        mice = EX[
            f"mice_{index}"
        ]

        # Measurement units can be reused across readings
        unit = EX[
            f"unit_{unit_key}"
        ]


        # ====================================================
        # ARTIFACT
        # ====================================================

        g.add(
            (
                artifact,
                RDF.type,
                CCO.Artifact
            )
        )

        g.add(
            (
                artifact,
                RDFS.label,
                Literal(
                    artifact_id,
                    lang="en"
                )
            )
        )


        # ====================================================
        # SPECIFICALLY DEPENDENT CONTINUANT
        # ====================================================

        g.add(
            (
                sdc,
                RDF.type,
                BFO.SpecificallyDependentContinuant
            )
        )

        g.add(
            (
                sdc,
                RDFS.label,
                Literal(
                    f"{artifact_id} {sdc_kind}",
                    lang="en"
                )
            )
        )


        # ====================================================
        # ARTIFACT BEARS SDC
        # ====================================================

        g.add(
            (
                artifact,
                BFO.bearer_of,
                sdc
            )
        )


        # ====================================================
        # MEASUREMENT INFORMATION CONTENT ENTITY
        # ====================================================

        g.add(
            (
                mice,
                RDF.type,
                MICE_CLASS
            )
        )


        # Give every MICE a unique label.
        #
        # This helps avoid triggering the project's
        # no_duplicate_labels.rq query.

        g.add(
            (
                mice,
                RDFS.label,
                Literal(
                    (
                        f"{artifact_id} "
                        f"{sdc_kind} "
                        f"measurement {index}"
                    ),
                    lang="en"
                )
            )
        )


        # ====================================================
        # MICE IS A MEASUREMENT OF THE SDC
        # ====================================================

        g.add(
            (
                mice,
                IS_MEASURE_OF,
                sdc
            )
        )


        # ====================================================
        # MICE HAS DECIMAL VALUE
        # ====================================================

        g.add(
            (
                mice,
                HAS_VALUE,
                Literal(
                    value,
                    datatype=XSD.decimal
                )
            )
        )


        # ====================================================
        # MEASUREMENT UNIT
        # ====================================================

        g.add(
            (
                unit,
                RDF.type,
                MEASUREMENT_UNIT_CLASS
            )
        )

        g.add(
            (
                unit,
                RDFS.label,
                Literal(
                    unit_label,
                    lang="en"
                )
            )
        )


        # ====================================================
        # MICE USES MEASUREMENT UNIT
        # ====================================================

        g.add(
            (
                mice,
                USES_MEASUREMENT_UNIT,
                unit
            )
        )


        # ====================================================
        # TIMESTAMP
        # ====================================================
        #
        # The normalized data contains a timestamp, but the
        # supplied CCO measurement design pattern does not
        # specify the exact property to use for connecting it.
        #
        # We therefore preserve it in the normalized CSV but
        # do not invent an ontology relation here.
        #
        # The variable remains available:
        #
        # timestamp
        #
        # if a later project instruction specifies how it
        # should be represented.


    # --------------------------------------------------------
    # 8. Create output directory if necessary.
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # 9. Serialize graph as Turtle.
    # --------------------------------------------------------

    g.serialize(
        destination=OUTPUT_FILE,
        format="turtle"
    )


    # --------------------------------------------------------
    # 10. Verify that the written file parses successfully.
    # --------------------------------------------------------

    test_graph = Graph()

    test_graph.parse(
        OUTPUT_FILE,
        format="turtle"
    )


    # --------------------------------------------------------
    # 11. Report results.
    # --------------------------------------------------------

    print()
    print("RDF generation complete.")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Input rows: {len(df)}")
    print(f"Triples generated: {len(g)}")
    print(
        f"Triples successfully parsed back: "
        f"{len(test_graph)}"
    )


# ============================================================
# RUN SCRIPT
# ============================================================

if __name__ == "__main__":
    main()