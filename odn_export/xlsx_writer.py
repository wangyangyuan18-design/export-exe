# -*- coding: utf-8 -*-
"""Small dependency-free XLSX writer for the plugin's fixed workbook layout."""

import zipfile
import xml.etree.ElementTree as ET

_NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_NS_PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
_NS_CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('', _NS_MAIN)
ET.register_namespace('r', _NS_REL)


def _tag(name):
    return '{%s}%s' % (_NS_MAIN, name)


def _col_name(index):
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(row_el, ref, value, style=None):
    attrs = {'r': ref}
    if style is not None:
        attrs['s'] = str(style)
    if value is None or value == '':
        ET.SubElement(row_el, _tag('c'), attrs)
        return
    if isinstance(value, bool):
        attrs['t'] = 'b'
        cell = ET.SubElement(row_el, _tag('c'), attrs)
        ET.SubElement(cell, _tag('v')).text = '1' if value else '0'
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        cell = ET.SubElement(row_el, _tag('c'), attrs)
        ET.SubElement(cell, _tag('v')).text = str(value)
    else:
        attrs['t'] = 'inlineStr'
        cell = ET.SubElement(row_el, _tag('c'), attrs)
        inline = ET.SubElement(cell, _tag('is'))
        text = ET.SubElement(inline, _tag('t'))
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = str(value)


def _row(sheet_data, row_number, values, styles=None):
    row = ET.SubElement(sheet_data, _tag('row'), {'r': str(row_number)})
    for col, value in enumerate(values, 1):
        style = styles[col - 1] if styles and col - 1 < len(styles) else None
        _cell(row, '{}{}'.format(_col_name(col), row_number), value, style)
    return row


def _worksheet_main(data_rows):
    root = ET.Element(_tag('worksheet'))
    views = ET.SubElement(root, _tag('sheetViews'))
    view = ET.SubElement(views, _tag('sheetView'), {'workbookViewId': '0', 'showGridLines': '0'})
    ET.SubElement(view, _tag('pane'), {'ySplit': '3', 'topLeftCell': 'A4', 'activePane': 'bottomLeft', 'state': 'frozen'})
    ET.SubElement(root, _tag('sheetFormatPr'), {'defaultRowHeight': '21'})
    cols = ET.SubElement(root, _tag('cols'))
    widths = [22, 24, 20, 16, 16, 18, 22, 24, 24, 12, 14]
    for idx, width in enumerate(widths, 1):
        ET.SubElement(cols, _tag('col'), {'min': str(idx), 'max': str(idx), 'width': str(width), 'customWidth': '1'})
    sheet_data = ET.SubElement(root, _tag('sheetData'))
    _row(sheet_data, 1, ['HUB BOX', '', '', '', 'Distribution Cable', '', 'SUB BOX', '', '', '', ''], [1] * 11)
    _row(sheet_data, 2, [
        'Hub Box Location', 'Floor No. / Pole No.', 'Hub Box ID', 'Hub Box Port',
        'SPAN', 'DIST. Cable Core', 'Subbox Location', 'Floor No. / Pole No.',
        'Subbox ID', 'HPs', 'Subbox Port'
    ], [2] * 11)
    _row(sheet_data, 3, [
        'HUB BOX所属杆子的坐标（纬度, 经度）', 'HUB BOX所属杆子的Name字段名称',
        'HUB BOX Name字段名称', '该SUB BOX所属链路（L1-L4）',
        '由 Distribution Cable 线几何推算的 Span 数量（请核对 QA Report）', '固定填1',
        'SUB BOX所属杆子的坐标（纬度, 经度）', 'SUB BOX所属杆子的Name字段名称',
        'SUB BOX Name字段名称', '同名 SUB BOX Boundary 内 6 个 Home Passed 图层要素数量', '固定填1'
    ], [3] * 11)
    for i, values in enumerate(data_rows, 4):
        _row(sheet_data, i, values, [4 if i % 2 == 0 else 5] * 11)
    ET.SubElement(root, _tag('mergeCells'), {'count': '3'})
    merges = root.find(_tag('mergeCells'))
    for ref in ('A1:D1', 'E1:F1', 'G1:K1'):
        ET.SubElement(merges, _tag('mergeCell'), {'ref': ref})
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _worksheet_report(qa, pole_radius_m):
    root = ET.Element(_tag('worksheet'))
    views = ET.SubElement(root, _tag('sheetViews'))
    ET.SubElement(views, _tag('sheetView'), {'workbookViewId': '0', 'showGridLines': '0'})
    ET.SubElement(root, _tag('sheetFormatPr'), {'defaultRowHeight': '20'})
    cols = ET.SubElement(root, _tag('cols'))
    for idx, width in enumerate([14, 24, 30, 38, 72], 1):
        ET.SubElement(cols, _tag('col'), {'min': str(idx), 'max': str(idx), 'width': str(width), 'customWidth': '1'})
    sheet_data = ET.SubElement(root, _tag('sheetData'))
    _row(sheet_data, 1, ['ODN Export QA Report', '', '', '', ''], [1] * 5)
    _row(sheet_data, 2, ['检查范围：杆子匹配半径 {} m'.format(pole_radius_m), '', '', '', ''], [3] * 5)
    _row(sheet_data, 3, ['Level', 'Layer / Type', 'Feature', 'Issue', 'Details'], [2] * 5)
    for i, record in enumerate(qa, 4):
        styles = [6 if record[0] == 'ERROR' else (7 if record[0] == 'WARNING' else 4)] * 5
        _row(sheet_data, i, record, styles)
    ET.SubElement(root, _tag('autoFilter'), {'ref': 'A3:E{}'.format(max(3, len(qa) + 3))})
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _styles_xml():
    root = ET.Element(_tag('styleSheet'))
    fonts = ET.SubElement(root, _tag('fonts'), {'count': '4'})
    f0 = ET.SubElement(fonts, _tag('font')); ET.SubElement(f0, _tag('sz'), {'val': '10'}); ET.SubElement(f0, _tag('name'), {'val': 'Arial'})
    f1 = ET.SubElement(fonts, _tag('font')); ET.SubElement(f1, _tag('b')); ET.SubElement(f1, _tag('color'), {'rgb': 'FFFFFFFF'}); ET.SubElement(f1, _tag('sz'), {'val': '12'}); ET.SubElement(f1, _tag('name'), {'val': 'Arial'})
    f2 = ET.SubElement(fonts, _tag('font')); ET.SubElement(f2, _tag('b')); ET.SubElement(f2, _tag('color'), {'rgb': 'FF17365D'}); ET.SubElement(f2, _tag('sz'), {'val': '10'}); ET.SubElement(f2, _tag('name'), {'val': 'Arial'})
    f3 = ET.SubElement(fonts, _tag('font')); ET.SubElement(f3, _tag('i')); ET.SubElement(f3, _tag('color'), {'rgb': 'FF555555'}); ET.SubElement(f3, _tag('sz'), {'val': '9'}); ET.SubElement(f3, _tag('name'), {'val': 'Arial'})
    fills = ET.SubElement(root, _tag('fills'), {'count': '5'})
    for pattern, color in [('none', None), ('gray125', None), ('solid', 'FF1F4E78'), ('solid', 'FFD9EAF7'), ('solid', 'FFF2F6FA')]:
        fill = ET.SubElement(fills, _tag('fill')); pf = ET.SubElement(fill, _tag('patternFill'), {'patternType': pattern})
        if color: ET.SubElement(pf, _tag('fgColor'), {'rgb': color}); ET.SubElement(pf, _tag('bgColor'), {'indexed': '64'})
    borders = ET.SubElement(root, _tag('borders'), {'count': '2'})
    ET.SubElement(borders, _tag('border'))
    border = ET.SubElement(borders, _tag('border'))
    for side in ('left', 'right', 'top', 'bottom'):
        ET.SubElement(border, _tag(side), {'style': 'thin'}).append(ET.Element(_tag('color'), {'rgb': 'FFD9E1F2'}))
    ET.SubElement(border, _tag('diagonal'))
    cell_style_xfs = ET.SubElement(root, _tag('cellStyleXfs'), {'count': '1'})
    ET.SubElement(cell_style_xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '0'})
    xfs = ET.SubElement(root, _tag('cellXfs'), {'count': '8'})
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '0', 'xfId': '0'})
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '1', 'fillId': '2', 'borderId': '1', 'xfId': '0', 'applyFont': '1', 'applyFill': '1', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'horizontal': 'center', 'vertical': 'center'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '2', 'fillId': '3', 'borderId': '1', 'xfId': '0', 'applyFont': '1', 'applyFill': '1', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'horizontal': 'center', 'vertical': 'center', 'wrapText': '1'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '3', 'fillId': '4', 'borderId': '1', 'xfId': '0', 'applyFont': '1', 'applyFill': '1', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'vertical': 'center', 'wrapText': '1'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '1', 'xfId': '0', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'vertical': 'center', 'wrapText': '1'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '4', 'borderId': '1', 'xfId': '0', 'applyBorder': '1', 'applyFill': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'vertical': 'center', 'wrapText': '1'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '1', 'xfId': '0', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'vertical': 'center', 'wrapText': '1'}))
    ET.SubElement(xfs, _tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '1', 'xfId': '0', 'applyBorder': '1', 'applyAlignment': '1'}).append(ET.Element(_tag('alignment'), {'vertical': 'center', 'wrapText': '1'}))
    cell_styles = ET.SubElement(root, _tag('cellStyles'), {'count': '1'})
    ET.SubElement(cell_styles, _tag('cellStyle'), {'name': 'Normal', 'xfId': '0', 'builtinId': '0'})
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def write_workbook(path, data_rows, qa_rows, pole_radius_m=3.0):
    """Write the two-sheet .xlsx workbook without external Python packages."""
    workbook = ET.Element(_tag('workbook'))
    sheets = ET.SubElement(workbook, _tag('sheets'))
    ET.SubElement(sheets, _tag('sheet'), {'name': 'ODN TRACE', 'sheetId': '1', '{%s}id' % _NS_REL: 'rId1'})
    ET.SubElement(sheets, _tag('sheet'), {'name': 'QA Report', 'sheetId': '2', '{%s}id' % _NS_REL: 'rId2'})
    workbook_xml = ET.tostring(workbook, encoding='utf-8', xml_declaration=True)

    rels = ET.Element('{%s}Relationships' % _NS_PKG_REL)
    ET.SubElement(rels, '{%s}Relationship' % _NS_PKG_REL, {'Id': 'rId1', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet', 'Target': 'worksheets/sheet1.xml'})
    ET.SubElement(rels, '{%s}Relationship' % _NS_PKG_REL, {'Id': 'rId2', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet', 'Target': 'worksheets/sheet2.xml'})
    ET.SubElement(rels, '{%s}Relationship' % _NS_PKG_REL, {'Id': 'rId3', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles', 'Target': 'styles.xml'})
    workbook_rels_xml = ET.tostring(rels, encoding='utf-8', xml_declaration=True)

    package_rels = ET.Element('{%s}Relationships' % _NS_PKG_REL)
    ET.SubElement(package_rels, '{%s}Relationship' % _NS_PKG_REL, {'Id': 'rId1', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument', 'Target': 'xl/workbook.xml'})
    package_rels_xml = ET.tostring(package_rels, encoding='utf-8', xml_declaration=True)

    content_types = ET.Element('{%s}Types' % _NS_CT)
    ET.SubElement(content_types, '{%s}Default' % _NS_CT, {'Extension': 'rels', 'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(content_types, '{%s}Default' % _NS_CT, {'Extension': 'xml', 'ContentType': 'application/xml'})
    ET.SubElement(content_types, '{%s}Override' % _NS_CT, {'PartName': '/xl/workbook.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'})
    ET.SubElement(content_types, '{%s}Override' % _NS_CT, {'PartName': '/xl/worksheets/sheet1.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
    ET.SubElement(content_types, '{%s}Override' % _NS_CT, {'PartName': '/xl/worksheets/sheet2.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
    ET.SubElement(content_types, '{%s}Override' % _NS_CT, {'PartName': '/xl/styles.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'})

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', ET.tostring(content_types, encoding='utf-8', xml_declaration=True))
        zf.writestr('_rels/.rels', package_rels_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        zf.writestr('xl/styles.xml', _styles_xml())
        zf.writestr('xl/worksheets/sheet1.xml', _worksheet_main(data_rows))
        zf.writestr('xl/worksheets/sheet2.xml', _worksheet_report(qa_rows, pole_radius_m))
