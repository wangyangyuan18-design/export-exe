# ODN Export Information (KMZ / QGIS)

QGIS 3 plugin for exporting the ODN Excel schedule from the final KMZ layer tree.

## KMZ structure supported

- Layer/group names may end with a numeric count, e.g. `Poles=374`, `New Pole=326`, `SUB BOX=14`, `Home Passed=209`; the suffix is ignored for matching.
- Pole features are collected recursively under `Poles` → `New Pole` and `Exsiting Pole` (also accepts `Existing Pole`) folders, including the 8m/10m child layers.
- SUB BOX points are collected from `SUB BOX(70/30)`, `SUB BOX(50/50)`, and `END BOX` child layers.
- HUB BOX, Distribution Cable, SUB BOX Boundary and six Home Passed layers are discovered recursively in hub groups.
- SUB BOX names such as `KIM-HB09L4S4` determine HUB ID, L link and S sequence. Output uses natural numeric order.
- HUB BOX and SUB BOX are matched separately to the closest pole within a user-configurable radius (8 m default). Exported coordinates and pole names come from the matched pole.
- HPs are calculated by summing the numeric `Name` values of point features in the six Home Passed categories (`Sdus`/`Sdu`, `Mdus`/`Mdu`, `Church`/`Churches`, `Commercial`, `Hospitals`/`Hospital`, `Institution`) that intersect the matching same-name `SUB BOX Boundary` polygon. Matching is case-insensitive and ignores spaces, punctuation, and an optional trailing plural `S`.
- No source layers or geometries are edited.

## Distribution Cable SPAN

KMZ does not preserve the previous `Span` attribute value. SPAN is the measured geodesic length of the matched Distribution Cable line geometry in metres (WGS84 ellipsoid), rounded to one decimal place. It is written as a numeric Excel value with a one-decimal number format.

## Installation

Download the build artifact from GitHub Actions and install it in QGIS using **Plugins → Manage and Install Plugins → Install from ZIP**.

Requirements: QGIS 3.22+; XLSX writing uses Python standard library only.
