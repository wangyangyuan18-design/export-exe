# -*- coding: utf-8 -*-
"""KMZ-only ODN extraction, spatial matching and Excel export."""
import math
import os
import re
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsGeometry, QgsPointXY, QgsProject, QgsDistanceArea)
from .kmz_tree import scan_project, home_passed_key, HOME_PASSED_NAMES
from .naming import clean_name, norm, parse_subbox_name, natural_hub_key
from .xlsx_writer import write_workbook

WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')
HP_LAYER_NAMES = HOME_PASSED_NAMES


def _feature_name(layer, feature):
    """Get the KMZ Placemark name (normally the sole Name field)."""
    fields = layer.fields()
    names = [f.name() for f in fields]
    name_field = next((n for n in names if norm(n) == 'NAME'), None)
    candidates = [name_field] if name_field else []
    candidates += [n for n in names if n not in candidates]
    for field_name in candidates:
        try:
            value = feature[field_name]
        except Exception:
            value = None
        if value is not None and str(value).strip():
            return clean_name(value)
    return ''


def _geom_wgs84(layer, feature, project, qa=None, kind='feature', name=''):
    geom = feature.geometry()
    if geom is None or geom.isNull() or geom.isEmpty():
        return None
    geom = QgsGeometry(geom)
    crs = layer.crs()
    if not crs.isValid():
        if qa is not None:
            qa.append(['ERROR', kind, name, '图层 CRS 无效', '无法进行可靠坐标换算和距离计算'])
        return None
    try:
        if crs != WGS84:
            geom.transform(QgsCoordinateTransform(crs, WGS84, project))
    except Exception as exc:
        if qa is not None:
            qa.append(['ERROR', kind, name, '坐标转换失败', str(exc)])
        return None
    if geom.isNull() or geom.isEmpty():
        return None
    return geom


def _point_lonlat(geom):
    if geom is None or geom.isEmpty():
        return None
    try:
        if geom.type() == 0:
            if geom.isMultipart():
                points = geom.asMultiPoint()
                if not points:
                    return None
                point = points[0]
            else:
                point = geom.asPoint()
        else:
            point = geom.centroid().asPoint()
        return (float(point.x()), float(point.y()))
    except Exception:
        return None


def _haversine_m(a, b):
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 6371008.8 * 2.0 * math.asin(min(1.0, math.sqrt(h)))


def _geometry_distance_m(point, geom):
    if point is None or geom is None or geom.isEmpty():
        return None
    try:
        pgeom = QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1]))
        nearest = geom.closestPoint(pgeom)
        if nearest is None or nearest.isEmpty():
            return None
        p = nearest.asPoint()
        return _haversine_m(point, (float(p.x()), float(p.y())))
    except Exception:
        return None


def _format_coord(point):
    if point is None:
        return ''
    lon, lat = point
    return '{:.6f}, {:.6f}'.format(lat, lon)


def _layer_records(layer_records, project, qa, kind):
    result = []
    for layer_rec in layer_records:
        layer = layer_rec['layer']
        path_hub = layer_rec['hub_from_path']
        for feature in layer.getFeatures():
            name = _feature_name(layer, feature)
            if not name and kind == 'HUB BOX':
                name = path_hub or ''
            geom = _geom_wgs84(layer, feature, project, qa, kind, name or str(feature.id()))
            if geom is None:
                continue
            point = _point_lonlat(geom)
            result.append({'name': name, 'geom': geom, 'point': point,
                           'hub': path_hub, 'path': layer_rec['path'],
                           'layer': layer.name(), 'fid': feature.id()})
    return result


def _nearest_pole(point, poles, radius_m):
    best, best_distance = None, None
    if point is None:
        return None, None
    for pole in poles:
        if pole['point'] is None:
            continue
        distance = _haversine_m(point, pole['point'])
        if best_distance is None or distance < best_distance:
            best, best_distance = pole, distance
    if best is not None and best_distance <= radius_m:
        return best, best_distance
    return None, best_distance


def _match_named(items, name, hub_id=None, point=None):
    candidates = [item for item in items if norm(item.get('name')) == norm(name)]
    if hub_id:
        same_group = [item for item in candidates if item.get('hub') == hub_id]
        if same_group:
            candidates = same_group
    if not candidates:
        return None, 0
    if len(candidates) == 1:
        return candidates[0], 1
    if point is not None:
        ranked = []
        for item in candidates:
            distance = _geometry_distance_m(point, item['geom'])
            if distance is not None:
                ranked.append((distance, item))
        if ranked:
            ranked.sort(key=lambda pair: pair[0])
            return ranked[0][1], len(candidates)
    return candidates[0], len(candidates)


def _same_hub(items, hub_id):
    exact = [item for item in items if item.get('hub') == hub_id]
    if exact:
        return exact
    return items


def _cable_span(cable, project, qa, sub_name):
    """Measure the Distribution Cable geometry length in metres on WGS84 ellipsoid."""
    try:
        distance = QgsDistanceArea()
        distance.setSourceCrs(WGS84, project.transformContext())
        distance.setEllipsoid('WGS84')
        length_m = float(distance.measureLength(cable['geom']))
        if not math.isfinite(length_m) or length_m <= 0:
            raise ValueError('线要素长度为 0 或无效')
        length_m = round(length_m, 1)
        qa.append(['INFO', 'Distribution Cable', sub_name, 'SPAN 直接读取线几何长度',
                   '测地长度：{:.1f} m（WGS84 椭球）。'.format(length_m)])
        return length_m
    except Exception as exc:
        qa.append(['ERROR', 'Distribution Cable', sub_name, '无法计算光缆几何长度', str(exc)])
        return ''


def _choose_cable(sub, hub_id, link_no, cables, qa):
    group_candidates = [item for item in cables if item.get('hub') == hub_id]
    if not group_candidates:
        group_candidates = [item for item in cables if norm(hub_id) in norm(item.get('name'))]
    if not group_candidates and len(cables) == 1:
        group_candidates = list(cables)
    if not group_candidates:
        return None

    # Best match: cable name contains the complete SUB BOX identifier.
    subbox_key = norm(sub['name'])
    exact = [c for c in group_candidates if subbox_key and subbox_key in norm(c['name'])]
    # Fallback: match the HUB + L-link, then use nearest geometry.
    if not exact:
        token = re.compile(r'L0*{}(?!\\d)'.format(int(link_no)), re.IGNORECASE)
        full_key = norm('{}L{}'.format(hub_id, link_no))
        exact = [c for c in group_candidates if full_key in norm(c['name'])]
        if not exact:
            exact = [c for c in group_candidates if token.search(clean_name(c['name']))]
    candidates = exact if exact else group_candidates
    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        ranked = []
        for cable in candidates:
            distance = _geometry_distance_m(sub['point'], cable['geom'])
            if distance is not None:
                ranked.append((distance, cable))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0])
        chosen = ranked[0][1]
    if not exact and len(group_candidates) > 1:
        qa.append(['WARNING', 'Distribution Cable', sub['name'], '无法从名称直接识别所属光缆',
                   '在所属 HUB 分组内按与 SUB BOX 最近的光缆选择；请复核 L{}。'.format(link_no)])
    return chosen, '名称精确匹配' if exact else '空间最近回退匹配'


def _count_home_passed(boundary_geom, hp_records, hub_id, qa, sub_name):
    scoped = [r for r in hp_records if r.get('hub') == hub_id]
    if not scoped:
        scoped = hp_records
        qa.append(['INFO', 'Home Passed', sub_name, 'Home Passed 图层使用全工程范围',
                   '当前未识别到与 HUB {} 同组的 HP 图层；仍按边界多边形进行空间筛选。'.format(hub_id)])
    count = 0
    by_layer = {}
    for record in scoped:
        try:
            if boundary_geom.intersects(record['geom']):
                count += 1
                by_layer[record['layer']] = by_layer.get(record['layer'], 0) + 1
        except Exception:
            pass
    return count, by_layer


def export_from_kmz_project(project, output_path, pole_radius_m=8.0, progress=None):
    qa = []
    found = scan_project(project)
    if not found['pole']:
        raise ValueError('未找到 Poles 组下 New Pole / Exsiting Pole 子图层。')
    if not found['sub_box']:
        raise ValueError('未找到 SUB BOX(70/30)、SUB BOX(50/50) 或 END BOX 图层。')
    if not found['subbox_boundary']:
        raise ValueError('未找到 SUB BOX Boundary 多边形图层。')
    if not found['home_passed']:
        raise ValueError('未找到 Home Passed 下的 Sdus、Mdus、Church、Commercial、Hospitals、Institution 图层。')

    poles = _layer_records(found['pole'], project, qa, 'Pole')
    hubs = _layer_records(found['hub_box'], project, qa, 'HUB BOX')
    subs = _layer_records(found['sub_box'], project, qa, 'SUB BOX')
    boundaries = _layer_records(found['subbox_boundary'], project, qa, 'SUB BOX Boundary')
    cables = _layer_records(found['distribution_cable'], project, qa, 'Distribution Cable')
    hp = _layer_records(found['home_passed'], project, qa, 'Home Passed')
    hp_layer_types = {home_passed_key(rec['layer_name']) for rec in found['home_passed']}
    missing_hp_types = sorted(HP_LAYER_NAMES - hp_layer_types)
    if missing_hp_types:
        qa.append(['WARNING', 'Home Passed', 'Project layer tree', '6 类 Home Passed 图层不完整',
                   '缺少图层：{}；HP 数量将按当前已识别到的图层统计。'.format(', '.join(missing_hp_types))])

    if not poles:
        raise ValueError('Poles 图层已识别，但没有可读取的有效杆子要素。')
    if not subs:
        raise ValueError('SUB BOX 图层已识别，但没有可读取的有效 SUB BOX 要素。')

    rows = []
    total = len(subs)
    matched_poles = 0
    total_pole_checks = 0
    missing_poles = 0
    missing_boundaries = 0
    duplicate_names = set()
    seen_names = set()
    for idx, sub in enumerate(subs):
        if progress and progress.wasCanceled():
            return {'cancelled': True}
        name = clean_name(sub['name'])
        parsed = parse_subbox_name(name)
        if not parsed:
            qa.append(['ERROR', 'SUB BOX', name or str(sub['fid']), 'SUB BOX 名称解析失败',
                       '预期格式：KIM-HB09L4S4（HUB ID + L 编号 + S 编号）。'])
            hub_id, link_no, seq_no = '', None, None
        else:
            hub_id, link_no, seq_no = parsed

        sub_pole, sub_dist = _nearest_pole(sub['point'], poles, pole_radius_m)
        total_pole_checks += 1
        sub_pole_name = _format_coord(sub_pole['point']) if sub_pole else ''
        sub_location = sub_pole_name
        if sub_pole:
            matched_poles += 1
            sub_pole_name = sub_pole['name']
        else:
            missing_poles += 1
            qa.append(['WARNING', 'SUB BOX', name, '8 米范围内未匹配到杆子',
                       '最近杆子距离：{}'.format('{:.2f} m'.format(sub_dist) if sub_dist is not None else '不可计算')])

        hub_rec, hub_dup = _match_named(hubs, hub_id, hub_id, sub['point']) if hub_id else (None, 0)
        if hub_dup > 1:
            qa.append(['WARNING', 'HUB BOX', hub_id, '同名 HUB BOX 要素重复',
                       '已优先选择相同 HUB 分组内或距离 SUB BOX 最近的要素。'])
        hub_pole_name, hub_location = '', ''
        if hub_rec:
            hub_pole, hub_dist = _nearest_pole(hub_rec['point'], poles, pole_radius_m)
            total_pole_checks += 1
            if hub_pole:
                matched_poles += 1
                hub_pole_name = hub_pole['name']
                hub_location = _format_coord(hub_pole['point'])
            else:
                missing_poles += 1
                qa.append(['WARNING', 'HUB BOX', hub_id, '8 米范围内未匹配到杆子',
                           '最近杆子距离：{}'.format('{:.2f} m'.format(hub_dist) if hub_dist is not None else '不可计算')])
        else:
            qa.append(['ERROR', 'HUB BOX', hub_id or name, '未找到对应 HUB BOX 点要素',
                       '按 SUB BOX 名称中的 HUB ID 在 KMZ HUB 分组/要素名中查找。'])

        boundary, boundary_dup = _match_named(boundaries, name, hub_id, sub['point'])
        hp_count = ''
        if boundary:
            hp_count, hp_breakdown = _count_home_passed(boundary['geom'], hp, hub_id, qa, name)
            if not hp_breakdown:
                qa.append(['INFO', 'Home Passed', name, '该 SUB BOX Boundary 内未统计到 HP 要素',
                           'HP Count = 0；请检查边界与 Home Passed 点位是否重叠。'])
            if boundary_dup > 1:
                qa.append(['WARNING', 'SUB BOX Boundary', name, '同名边界多边形重复',
                           '已优先按 HUB 分组并按与 SUB BOX 最近的多边形选择。'])
        else:
            missing_boundaries += 1
            qa.append(['ERROR', 'SUB BOX Boundary', name, '未找到同名 SUB BOX Boundary 多边形',
                       'HPs 留空；请检查边界图层要素名称是否与 SUB BOX 名称一致。'])

        span = ''
        if parsed:
            chosen = _choose_cable(sub, hub_id, link_no, cables, qa)
            if chosen:
                cable_rec, _method = chosen
                span = _cable_span(cable_rec, project, qa, name)
            else:
                qa.append(['WARNING', 'Distribution Cable', name, '未找到所属 HUB 的光缆线要素',
                           'KMZ 中没有可用 Distribution Cable 几何，SPAN 留空。'])

        if norm(name) in seen_names:
            duplicate_names.add(norm(name))
            qa.append(['WARNING', 'SUB BOX', name, 'SUB BOX 名称重复', '重复记录均保留在导出表中。'])
        seen_names.add(norm(name))
        rows.append({
            'key': (natural_hub_key(hub_id), link_no if link_no is not None else 999999,
                    seq_no if seq_no is not None else 999999, name.upper()),
            'values': [hub_location, hub_pole_name, hub_id,
                       'L{}'.format(link_no) if link_no is not None else '', span, 1,
                       sub_location, sub_pole_name, name, hp_count, 1]
        })
        if progress:
            progress.setLabelText('正在计算 SUB BOX HP 与杆子匹配：{} / {}'.format(idx + 1, total))
            progress.setValue(int((idx + 1) * 100.0 / max(1, total)))

    rows.sort(key=lambda r: r['key'])
    if progress and progress.wasCanceled():
        return {'cancelled': True}
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    write_workbook(output_path, [r['values'] for r in rows], qa, pole_radius_m)
    return {'cancelled': False, 'rows': len(rows), 'matched': matched_poles,
            'total': total_pole_checks, 'missing_poles': missing_poles,
            'missing_boundaries': missing_boundaries, 'qa_count': len(qa),
            'path': output_path, 'layer_counts': {k: len(v) for k, v in found.items()}}
