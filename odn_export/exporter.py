# -*- coding: utf-8 -*-
"""Export the ODN Excel schedule from a user-selected KMZ/KML source file."""
import math
import os
from decimal import Decimal, InvalidOperation

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
                       QgsDistanceArea, QgsGeometry, QgsPointXY)

from .kml_source import load_kml_source
from .naming import clean_name, norm, parse_subbox_name, natural_hub_key
from .rules import numeric_hp_value, cable_subbox_target
from .xlsx_writer import write_workbook

WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')


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
        return float(point.x()), float(point.y())
    except Exception:
        return None


def _haversine_m(a, b):
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = (math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2)
         * math.sin(dlon / 2.0) ** 2)
    return 6371008.8 * 2.0 * math.asin(min(1.0, math.sqrt(h)))


def _geometry_distance_m(point, geometry):
    if point is None or geometry is None or geometry.isEmpty():
        return None
    try:
        point_geom = QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1]))
        nearest = geometry.closestPoint(point_geom)
        if nearest is None or nearest.isEmpty():
            return None
        nearest_point = nearest.asPoint()
        return _haversine_m(point, (float(nearest_point.x()), float(nearest_point.y())))
    except Exception:
        return None


def _format_coord(point):
    if point is None:
        return ''
    lon, lat = point
    return '{:.6f}, {:.6f}'.format(lat, lon)


def _nearest_pole(point, poles, radius_m):
    best, best_distance = None, None
    if point is None:
        return None, None
    for pole in poles:
        if pole.get('point') is None:
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
        same_hub = [item for item in candidates if item.get('hub') == hub_id]
        if same_hub:
            candidates = same_hub
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
            ranked.sort(key=lambda value: value[0])
            return ranked[0][1], len(candidates)
    return candidates[0], len(candidates)


def _decimal_to_excel(value):
    if value == value.to_integral_value():
        return int(value)
    return round(float(value), 2)


def _count_home_passed(boundary_geom, hp_records, hub_id, qa, sub_name):
    """Sum available HP categories in this SUB BOX's own HUB only.

    Missing individual categories are allowed. If this HUB contains no Home
    Passed category at all, HPs is left blank rather than borrowing another
    HUB's points. If there are source records but none intersects the boundary,
    HPs is numeric zero.
    """
    scoped = [record for record in hp_records if record.get('hub') == hub_id]
    if not scoped:
        qa.append([
            'ERROR', 'Home Passed', sub_name,
            '该 SUB BOX 所属 HUB 没有可用的 Home Passed 图层',
            '本 HUB 未发现六类 Home Passed 中的任何一类；为避免跨 HUB 误计，HPs 留空。'
        ])
        return '', {}

    total = Decimal('0')
    numeric_feature_count = 0
    by_layer = {}
    non_numeric = []

    for record in scoped:
        try:
            if not boundary_geom.intersects(record['geom']):
                continue
        except Exception as exc:
            qa.append(['WARNING', 'Home Passed', sub_name, '点与 SUB BOX Boundary 空间判断失败', str(exc)])
            continue

        raw_name = str(record.get('name') or '').strip()
        try:
            units = numeric_hp_value(raw_name)
        except (InvalidOperation, ValueError, TypeError):
            non_numeric.append((record.get('layer', ''), raw_name))
            continue

        total += units
        numeric_feature_count += 1
        layer_name = record.get('layer') or 'Home Passed'
        by_layer[layer_name] = by_layer.get(layer_name, Decimal('0')) + units

    for layer_name, bad_name in non_numeric:
        qa.append([
            'WARNING', 'Home Passed', sub_name,
            '边界内 HP 要素的 Name 不是数值，未计入合计',
            '图层：{}；Name：{}'.format(layer_name, bad_name)
        ])

    if numeric_feature_count == 0:
        if non_numeric:
            qa.append([
                'WARNING', 'Home Passed', sub_name,
                '边界内没有可转换为数值的 HP 要素',
                'HPs = 0；请检查上方非数值 Name 记录。'
            ])
        else:
            qa.append([
                'INFO', 'Home Passed', sub_name,
                '该 SUB BOX Boundary 内未统计到数值型 HP 要素',
                'HPs = 0；请检查 Boundary 与当前 HUB 的 Home Passed 点位是否重叠。'
            ])

    return _decimal_to_excel(total), by_layer


def _cable_span(cable, qa, sub_name):
    """Measure the actual Distribution Cable line geometry in WGS84 metres."""
    try:
        distance = QgsDistanceArea()
        distance.setSourceCrs(WGS84, QgsCoordinateTransformContext())
        distance.setEllipsoid('WGS84')
        length_m = float(distance.measureLength(cable['geom']))
        if not math.isfinite(length_m) or length_m <= 0:
            raise ValueError('线要素长度为 0 或无效')
        length_m = round(length_m, 1)
        qa.append([
            'INFO', 'Distribution Cable', sub_name,
            'SPAN 直接读取线几何长度',
            '测地长度：{:.1f} m（WGS84 椭球）；按线名最后一个 SUB BOX 端点归属。'.format(length_m)
        ])
        return length_m
    except Exception as exc:
        qa.append(['ERROR', 'Distribution Cable', sub_name, '无法计算光缆几何长度', str(exc)])
        return ''


def _map_cables_to_subboxes(cables, subs, qa):
    """Map each cable to its right-hand/last SUB BOX endpoint.

    Examples:
      HUB-A -> A
      A-B   -> B

    This is intentionally not scoped by HUB group and does not use nearest-line
    fallback. Each Distribution Cable is assigned to exactly one SUB BOX.
    """
    sub_names = [sub.get('name', '') for sub in subs]

    mapped = {}
    unmatched_cables = []
    for cable in cables:
        target_name, hit_names = cable_subbox_target(cable.get('name', ''), sub_names)
        if not target_name:
            unmatched_cables.append(cable)
            qa.append([
                'WARNING', 'Distribution Cable', cable.get('name', ''),
                '无法从 DC 线名识别 SUB BOX 归属',
                '没有匹配到任何 SUB BOX 完整 ID；该条光缆不会按 HUB 或距离强行分配。'
            ])
            continue

        # The last complete SUB BOX ID contained in the cable name owns the line.
        target_key = norm(target_name)
        mapped.setdefault(target_key, []).append(cable)
        if len(hit_names) > 1:
            qa.append([
                'INFO', 'Distribution Cable', cable.get('name', ''),
                '双端点光缆按末端 SUB BOX 归属',
                '检测到多个 SUB BOX 端点，按命名规则归属到 {}。'.format(target_name)
            ])

    return mapped, unmatched_cables


def _select_cable_for_sub(sub, mapped, qa):
    candidates = mapped.get(norm(sub.get('name')), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Duplicate names are exceptional; select the line spatially closest to
    # this SUB BOX and report all duplicates for manual review.
    ranked = []
    for cable in candidates:
        distance = _geometry_distance_m(sub.get('point'), cable['geom'])
        ranked.append((float('inf') if distance is None else distance, cable))
    ranked.sort(key=lambda value: value[0])
    qa.append([
        'WARNING', 'Distribution Cable', sub.get('name', ''),
        '同一个 SUB BOX 匹配到多条 Distribution Cable',
        '候选数量：{}；已选取线几何距离最近的一条，请复核。'.format(len(candidates))
    ])
    return ranked[0][1]


def _records_for_hub(records, hub_id):
    return [record for record in records if record.get('hub') == hub_id]


def export_from_kml_file(source_path, output_path, pole_radius_m=8.0,
                         progress=None, source_data=None):
    """Export Excel from the selected KMZ/KML file, independent of QGIS layers."""
    found = source_data if source_data is not None else load_kml_source(source_path)
    qa = list(found.get('source_qa', []))
    poles = found.get('pole', [])
    hubs = found.get('hub_box', [])
    subs = found.get('sub_box', [])
    boundaries = found.get('subbox_boundary', [])
    cables = found.get('distribution_cable', [])
    hp_records = found.get('home_passed', [])

    if not subs:
        raise ValueError('所选 KMZ/KML 中未识别到 SUB BOX(70/30)、SUB BOX(50/50) 或 END BOX 点要素。')

    if not poles:
        qa.append(['WARNING', 'Pole', 'Source KMZ/KML', '未识别到杆子图层', '仍继续导出，所有杆子位置字段留空。'])
    if not boundaries:
        qa.append(['ERROR', 'SUB BOX Boundary', 'Source KMZ/KML', '未识别到 SUB BOX Boundary', '所有 HPs 留空；请检查 KMZ/KML 图层文件夹。'])
    if not cables:
        qa.append(['WARNING', 'Distribution Cable', 'Source KMZ/KML', '未识别到 Distribution Cable', '所有 SPAN 留空。'])

    cable_map, unmatched_cables = _map_cables_to_subboxes(cables, subs, qa)
    if len(cables) != len(subs):
        qa.append([
            'WARNING', 'Distribution Cable', 'Source KMZ/KML',
            'SUB BOX 数量与 Distribution Cable 数量不一致',
            'SUB BOX：{}；Distribution Cable：{}；不能一一对应的记录会在 ODN TRACE / QA Report 中留痕。'.format(len(subs), len(cables))
        ])

    rows = []
    matched_poles = 0
    total_pole_checks = 0
    missing_poles = 0
    missing_boundaries = 0
    matched_cables = 0
    matched_hp = 0
    seen_names = set()

    for index, sub in enumerate(subs):
        if progress and progress.wasCanceled():
            return {'cancelled': True}

        name = clean_name(sub.get('name'))
        parsed = parse_subbox_name(name)
        if not parsed:
            qa.append([
                'ERROR', 'SUB BOX', name or str(sub.get('fid')),
                'SUB BOX 名称解析失败',
                '预期格式：KIM-HB09L4S4（HUB ID + L 编号 + S 编号）。'
            ])
            hub_id, link_no, seq_no = '', None, None
        else:
            hub_id, link_no, seq_no = parsed

        # SUB BOX -> nearest pole
        sub_pole, sub_distance = _nearest_pole(sub.get('point'), poles, pole_radius_m)
        total_pole_checks += 1
        sub_location = _format_coord(sub_pole.get('point')) if sub_pole else ''
        sub_pole_name = sub_pole.get('name', '') if sub_pole else ''
        if sub_pole:
            matched_poles += 1
        else:
            missing_poles += 1
            qa.append([
                'WARNING', 'SUB BOX', name, '匹配半径内未匹配到杆子',
                '匹配半径：{:.1f} m；最近杆子距离：{}'.format(
                    pole_radius_m,
                    '{:.2f} m'.format(sub_distance) if sub_distance is not None else '不可计算'
                )
            ])

        # HUB BOX -> nearest pole
        hub_rec, hub_duplicates = _match_named(hubs, hub_id, hub_id, sub.get('point')) if hub_id else (None, 0)
        hub_pole_name, hub_location = '', ''
        if hub_duplicates > 1:
            qa.append([
                'WARNING', 'HUB BOX', hub_id, '同名 HUB BOX 要素重复',
                '已优先选择同一 HUB 文件夹内、距离 SUB BOX 最近的点要素。'
            ])
        if hub_rec:
            hub_pole, hub_distance = _nearest_pole(hub_rec.get('point'), poles, pole_radius_m)
            total_pole_checks += 1
            if hub_pole:
                matched_poles += 1
                hub_pole_name = hub_pole.get('name', '')
                hub_location = _format_coord(hub_pole.get('point'))
            else:
                missing_poles += 1
                qa.append([
                    'WARNING', 'HUB BOX', hub_id, '匹配半径内未匹配到杆子',
                    '匹配半径：{:.1f} m；最近杆子距离：{}'.format(
                        pole_radius_m,
                        '{:.2f} m'.format(hub_distance) if hub_distance is not None else '不可计算'
                    )
                ])
        else:
            qa.append([
                'ERROR', 'HUB BOX', hub_id or name, '未找到对应 HUB BOX 点要素',
                '按 SUB BOX 名称中的 HUB ID 查找同名 HUB BOX。'
            ])

        # HP is strictly scoped to this SUB BOX's own HUB and its own boundary.
        boundary, boundary_duplicates = _match_named(boundaries, name, hub_id, sub.get('point'))
        hp_count = ''
        if boundary:
            hp_count, hp_breakdown = _count_home_passed(boundary['geom'], hp_records, hub_id, qa, name)
            if hp_count != '':
                matched_hp += 1
            if boundary_duplicates > 1:
                qa.append([
                    'WARNING', 'SUB BOX Boundary', name, '同名边界多边形重复',
                    '已优先选择同一 HUB 下距离 SUB BOX 最近的多边形。'
                ])
        else:
            missing_boundaries += 1
            qa.append([
                'ERROR', 'SUB BOX Boundary', name, '未找到同名 SUB BOX Boundary 多边形',
                'HPs 留空；请检查 Boundary 要素名称是否与 SUB BOX 名称一致。'
            ])

        # Distribution Cable is assigned by the last SUB BOX endpoint in its name.
        span = ''
        cable = _select_cable_for_sub(sub, cable_map, qa)
        if cable:
            matched_cables += 1
            span = _cable_span(cable, qa, name)
        else:
            qa.append([
                'WARNING', 'Distribution Cable', name, '未匹配到归属于该 SUB BOX 的光缆',
                '规则：HUB-A 归属 A；A-B 归属 B。未按 HUB 分组或空间最近距离进行猜测，SPAN 留空。'
            ])

        key_name = norm(name)
        if key_name in seen_names:
            qa.append(['WARNING', 'SUB BOX', name, 'SUB BOX 名称重复', '重复记录均保留在导出表中。'])
        seen_names.add(key_name)

        rows.append({
            'key': (natural_hub_key(hub_id), link_no if link_no is not None else 999999,
                    seq_no if seq_no is not None else 999999, name.upper()),
            'values': [hub_location, hub_pole_name, hub_id,
                       'L{}'.format(link_no) if link_no is not None else '', span, 1,
                       sub_location, sub_pole_name, name, hp_count, 1]
        })

        if progress:
            progress.setLabelText('正在处理 SUB BOX：{} / {}'.format(index + 1, len(subs)))
            progress.setValue(int((index + 1) * 100.0 / max(1, len(subs))))

    rows.sort(key=lambda row: row['key'])
    if progress and progress.wasCanceled():
        return {'cancelled': True}

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    write_workbook(output_path, [row['values'] for row in rows], qa, pole_radius_m)

    return {
        'cancelled': False,
        'rows': len(rows),
        'matched': matched_poles,
        'total': total_pole_checks,
        'missing_poles': missing_poles,
        'missing_boundaries': missing_boundaries,
        'qa_count': len(qa),
        'cable_matched': matched_cables,
        'cable_total': len(cables),
        'hp_matched': matched_hp,
        'hp_feature_count': len(hp_records),
        'pole_radius_m': pole_radius_m,
        'path': output_path,
        'source': found.get('source_path', source_path),
        'layer_counts': {key: len(found.get(key, [])) for key in (
            'pole', 'hub_box', 'sub_box', 'subbox_boundary', 'distribution_cable', 'home_passed'
        )},
    }