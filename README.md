# ODN Export Information (KMZ / QGIS)

QGIS 3 plugin for exporting the ODN Excel schedule from the final KMZ layer tree.

## KMZ structure supported

- Layer/group names may end with a numeric count, e.g. `Poles=374`, `New Pole=326`, `SUB BOX=14`, `Home Passed=209`; the suffix is ignored for matching.
- Pole features are collected recursively under `Poles` → `New Pole` and `Exsiting Pole` (also accepts `Existing Pole`) folders, including the 8m/10m child layers.
- SUB BOX points are collected from `SUB BOX(70/30)`, `SUB BOX(50/50)`, and `END BOX` child layers.
- HUB BOX, Distribution Cable, SUB BOX Boundary and six Home Passed layers are discovered recursively in hub groups.
- SUB BOX names such as `KIM-HB09L4S4` determine HUB ID, L link and S sequence. Output uses natural numeric order.
- HUB BOX and SUB BOX are matched separately to the closest pole within a user-configurable radius (8 m default). Exported coordinates and pole names come from the matched pole.
- HPs are calculated by counting point features in the six Home Passed layers (`Sdus`, `Mdus`, `Church`, `Commercial`, `Hospitals`, `Institution`) that intersect the matching same-name `SUB BOX Boundary` polygon.
- No source layers or geometries are edited.

## Distribution Cable SPAN

KMZ does not preserve the previous `Span` attribute value. The plugin derives SPAN from the cable geometry: when at least two pole points are found along the selected cable, SPAN is the number of matched pole intervals; otherwise it uses the line geometry's vertex-segment count. Derived values are flagged in the QA worksheet so they can be checked against the source design.

## Installation

Download the build artifact from GitHub Actions and install it in QGIS using **Plugins → Manage and Install Plugins → Install from ZIP**.

Requirements: QGIS 3.22+; XLSX writing uses Python standard library only.
