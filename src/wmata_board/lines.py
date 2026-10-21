"""The six Metrorail lines, in the two vocabularies WMATA uses.

The JSON APIs say "OR"; the GTFS feeds say "ORANGE". Everything we serve
uses the two-letter codes, so GTFS route_ids are mapped here on ingest.
"""

LINE_CODES = ("RD", "OR", "SV", "BL", "GR", "YL")

ROUTE_LINES = {
    "RED": "RD",
    "ORANGE": "OR",
    "SILVER": "SV",
    "BLUE": "BL",
    "GREEN": "GR",
    "YELLOW": "YL",
}

# Lines that run mostly north-south: their shapes are oriented S->N, the rest
# W->E, so lines sharing track run the same way and lane offsets stay on
# consistent sides.
NORTH_SOUTH = frozenset({"GR", "YL"})
