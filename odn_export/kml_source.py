# -*- coding: utf-8 -*-
"""Read KMZ/KML directly, without relying on the currently open QGIS project."""
import os
import zipfile
import xml.etree.ElementTree as ET

from qgis.core import QgsGeometry

from .kmz_tree import classify_layer, hub_for_path
from .naming import clean_name


_SUPPORTED_GEOMETRIES = {'Point', 'LineString', 'Polygon', 'MultiGeometry'}


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _children(element, wanted):
    return [child for child in list(element) if _local_name(child.tag) == wanted]


def _first_descendant(element, wanted):
    for child in element.iter():
        if child is not element and _local_name(child.tag) == wanted:
            return child
    return None


def _folder_name(folder):
    node = _first_descendant(folder, 'name')
    return (node.text or '').strip() if node is not None else ''


def _coordinates(element):
    """Parse KML coordinates (longitude, latitude[, altitude])."""
    if element is None or not (element.text or '').strip():
        return []
    result = []
    for token in (element.text or '').replace('\n', ' ').replace('\t', ' ').split():
        values = token.split(',')
        if len(values) < 2:
            continue
        try:
            x, y = float(values[0]), float(values[1])
        except (TypeError, ValueError):
            continue
        # KML altitude is intentionally ignored; all spatial work is 2D WGS84.
        result.append((x, y))
    return result


def _coord_text(points):
    return ', '.join('{:.12g} {:.12g}'.format(x, y) for x, y in points)


def _linear_ring_wkt(ring):
    coords = _first_descendant(ring, 'coordinates')
    points = _coordinates(coords)
    if len(points) < 3:
        return None
    if points[0] != points[-1]:
        points.append(points[0])
    return '(' + _coord_text(points) + ')'


def _geometry_wkt(element):
    """Convert the common KML geometry elements to standards-based WKT."""
    kind = _local_name(element.tag)
    if kind == 'Point':
        points = _coordinates(_first_descendant(element, 'coordinates'))
        return 'POINT ({})'.format(_coord_text(points[:1])) if points else None

    if kind == 'LineString':
        points = _coordinates(_first_descendant(element, 'coordinates'))
        return 'LINESTRING ({})'.format(_coord_text(points)) if len(points) >= 2 else None

    if kind == 'Polygon':
        rings = []
        for boundary in element.iter():
            if _local_name(boundary.tag) != 'LinearRing':
                continue
            ring_wkt = _linear_ring_wkt(boundary)
            if ring_wkt:
                rings.append(ring_wkt)
        return 'POLYGON ({})'.format(', '.join(rings)) if rings else None

    if kind == 'MultiGeometry':
        parts = []
        for child in list(element):
            if _local_name(child.tag) in _SUPPORTED_GEOMETRIES:
                child_wkt = _geometry_wkt(child)
                if child_wkt:
                    parts.append(child_wkt)
        return 'GEOMETRYCOLLECTION ({})'.format(', '.join(parts)) if parts else None

    return None


def _placemark_geometry(placemark):
    parts = []
    for child in list(placemark):
        if _local_name(child.tag) in _SUPPORTED_GEOMETRIES:
            value = _geometry_wkt(child)
            if value:
                parts.append(value)
    if not parts:
        return None
    wkt = parts[0] if len(parts) == 1 else 'GEOMETRYCOLLECTION ({})'.format(', '.join(parts))
    geometry = QgsGeometry.fromWkt(wkt)
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return None
    return geometry


def _placemark_name(placemark):
    node = _first_descendant(placemark, 'name')
    return clean_name(node.text if node is not None else '')


def _open_kml_bytes(source_path):
    extension = os.path.splitext(source_path)[1].lower()
    if extension == '.kmz':
        with zipfile.ZipFile(source_path, 'r') as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith('.kml')]
            if not kml_names:
                raise ValueError('KMZ 文件内没有找到 KML 文档。')
            # doc.kml is the standard root document; otherwise use first KML entry.
            selected = next((name for name in kml_names if name.lower().endswith('/doc.kml') or name.lower() == 'doc.kml'), kml_names[0])
            return archive.read(selected), selected
    if extension == '.kml':
        with open(source_path, 'rb') as handle:
            return handle.read(), os.path.basename(source_path)
    raise ValueError('仅支持 .kmz 或 .kml 源文件。')


def load_kml_source(source_path):
    """Read all classified placemarks from a user-selected KMZ/KML file.

    Returned geometries are WGS84 and have no dependency on QgsProject layers,
    layer visibility, project groups, or the project currently open in QGIS.
    """
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise ValueError('源文件不存在：{}'.format(source_path))

    payload, kml_entry = _open_kml_bytes(source_path)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError('KML/XML 解析失败：{}'.format(exc))

    categories = ('pole', 'hub_box', 'sub_box', 'subbox_boundary',
                  'distribution_cable', 'home_passed')
    found = {key: [] for key in categories}
    found['other'] = []
    found['source_qa'] = []
    feature_id = 0

    def walk(node, folder_path):
        nonlocal feature_id
        for child in list(node):
            kind = _local_name(child.tag)
            if kind == 'Folder':
                walk(child, folder_path + (_folder_name(child),))
                continue
            if kind != 'Placemark':
                # Document, kml and Style elements can contain Folder descendants.
                if kind in ('kml', 'Document'):
                    walk(child, folder_path)
                continue

            feature_id += 1
            if not folder_path:
                continue

            # Look upwards so that an optional subfolder below a semantic folder
            # does not cause the placemark to disappear from the export.
            category = None
            category_index = None
            for index in range(len(folder_path) - 1, -1, -1):
                candidate = classify_layer(folder_path[index], folder_path[:index])
                if candidate:
                    category, category_index = candidate, index
                    break
            if not category:
                continue

            geometry = _placemark_geometry(child)
            name = _placemark_name(child)
            ancestors = folder_path[:category_index]
            hub_id = hub_for_path(ancestors)
            if not name and category == 'hub_box':
                name = hub_id or ''
            if geometry is None:
                found['source_qa'].append([
                    'WARNING', category, name or 'Placemark #{}'.format(feature_id),
                    '要素几何为空或格式不支持',
                    '源文件：{}；文件夹：{}'.format(kml_entry, ' / '.join(folder_path))
                ])
                continue

            point = _geometry_point(geometry)
            record = {
                'name': name,
                'geom': geometry,
                'point': point,
                'hub': hub_id,
                'path': folder_path,
                'layer': clean_name(folder_path[category_index]),
                'layer_name': clean_name(folder_path[category_index]),
                'fid': feature_id,
            }
            found[category].append(record)

    walk(root, ())
    found['source_path'] = source_path
    found['kml_entry'] = kml_entry
    return found


def _geometry_point(geometry):
    """Return a geometry's representative point as (longitude, latitude)."""
    try:
        if geometry.type() == 0:  # QGIS point geometry
            if geometry.isMultipart():
                points = geometry.asMultiPoint()
                if not points:
                    return None
                point = points[0]
            else:
                point = geometry.asPoint()
        else:
            point = geometry.centroid().asPoint()
        return float(point.x()), float(point.y())
    except Exception:
        return None


def summarize_source(found):
    """Compact feature counts for the scan preview and QA summary."""
    keys = ('pole', 'hub_box', 'sub_box', 'subbox_boundary', 'distribution_cable', 'home_passed')
    return {key: len(found.get(key, [])) for key in keys}