# ODN Export Information (KMZ / KML)

QGIS 3 plugin for exporting the ODN Excel schedule directly from a selected KMZ/KML source file. The currently open QGIS project and its layer tree are not used as the data source.

## Source file and folder structure

- Select a `.kmz` or `.kml` file in the plugin. The standard `doc.kml` inside a KMZ is preferred; otherwise the first KML document is read.
- Folder and layer names may end with a numeric count, e.g. `Poles=374`, `New Pole=326`, `SUB BOX=14`, `Home Passed=209`; the suffix is ignored.
- Pole features are collected recursively under `Poles` → `New Pole` / `Exsiting Pole` (also accepts `Existing Pole`) and their child folders.
- SUB BOX points are read from all three point categories: `SUB BOX(70/30)`, `SUB BOX(50/50)`, and `END BOX`. No subtype is skipped.
- HUB BOX, SUB BOX Boundary, Distribution Cable and Home Passed categories are read from the selected source's folder hierarchy.

## Distribution Cable assignment and SPAN

Every Distribution Cable is assigned to one SUB BOX based on the complete SUB BOX IDs contained in the cable's name:

- `HUB-A` belongs to SUB BOX **A**.
- `A-B` belongs to SUB BOX **B** (the last/right-hand SUB BOX endpoint).

The assignment is based on the cable name, not HUB folder membership or nearest-line fallback. The expected source pattern is one Distribution Cable for each SUB BOX. Unmatched/duplicate lines are listed in `QA Report`.

SPAN is the measured geodesic length of the matched Distribution Cable line geometry in metres (WGS84 ellipsoid), rounded to one decimal place and written as a numeric Excel cell.

## HPs calculation

- HPs are calculated for each SUB BOX separately, using its same-name `SUB BOX Boundary` polygon.
- Only Home Passed features in that SUB BOX's own HUB folder are considered; points from other HUBs are never borrowed.
- The six categories are optional individually. When a HUB contains only some of `Sdus`, `Mdus`, `Church`, `Commercial`, `Hospitals`, `Institution`, all available categories are summed.
- The numeric value in each Home Passed Placemark `Name` is converted to a number and summed for points intersecting the SUB BOX Boundary.
- If the HUB has no Home Passed category at all, HPs is left blank and explained in `QA Report`. If the HUB has Home Passed data but no numeric point falls inside the boundary, HPs is `0`. Non-numeric names are reported and excluded from the sum.

## Pole matching

HUB BOX and SUB BOX points are independently matched to the closest pole within a user-configurable radius (8 m default). Exported coordinates are in latitude, longitude order and pole names come from the matched pole feature. Missing pole matches remain blank and are reported in `QA Report`.

## Excel output

The workbook contains `ODN TRACE` and `QA Report`. No source KMZ/KML geometry or attribute is edited.

## Installation

Download the build artifact from GitHub Actions and install in QGIS using **Plugins → Manage and Install Plugins → Install from ZIP**.

Requirements: QGIS 3.22+; XLSX writing uses Python standard library only.