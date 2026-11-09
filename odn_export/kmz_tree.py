# -*- coding: utf-8 -*-
"""Discover semantic layers and group paths in a QGIS project loaded from KMZ."""
from .naming import clean_name, norm, hub_from_group_name

HOME_PASSED_NAMES = {'SDU', 'MDU', 'CHURCH', 'COMMERCIAL', 'HOSPITAL', 'INSTITUTION'}


def home_passed_key(value):
    # Canonicalise HP layer names, accepting optional plural forms and case changes.
    value = norm(value)
    if value == 'CHURCHES':
        return 'CHURCH'
    if value.endswith('S'):
        value = value[:-1]
    return value
POLE_GROUP_NAMES = {'NEWPOLE', 'EXSITINGPOLE', 'EXISTINGPOLE'}
SUBBOX_POINT_NAMES = {'SUBBOX7030', 'SUBBOX5050', 'ENDBOX'}

def _is_group(node):
    return hasattr(node, 'children') and not hasattr(node, 'layer')

def walk_layer_tree(root):
    """Yield (layer, cleaned_group_path, cleaned_layer_name)."""
    def walk(node, path):
        for child in node.children():
            if hasattr(child, 'layer') and callable(child.layer):
                layer = child.layer()
                if layer and layer.isValid():
                    yield layer, tuple(path), clean_name(child.name())
            elif _is_group(child):
                yield from walk(child, path + [clean_name(child.name())])
    yield from walk(root, [])

def _has_pole_ancestor(path):
    return any(norm(part) in POLE_GROUP_NAMES for part in path)

def classify_layer(layer_name, group_path):
    leaf = norm(layer_name)
    path_norm = [norm(p) for p in group_path]
    if _has_pole_ancestor(group_path) or leaf.startswith('NEWPOLE') or leaf.startswith('EXSITINGPOLE') or leaf.startswith('EXISTINGPOLE'):
        return 'pole'
    if leaf == 'HUBBOX' or (leaf.startswith('HUBBOX') and 'BOUNDARY' not in leaf):
        return 'hub_box'
    if 'SUBBOXBOUNDARY' in leaf:
        return 'subbox_boundary'
    if leaf in SUBBOX_POINT_NAMES:
        return 'sub_box'
    if 'DISTRIBUTIONCABLE' in leaf:
        return 'distribution_cable'
    hp_key = home_passed_key(layer_name)
    if hp_key in HOME_PASSED_NAMES and 'HOMEPASSED' in path_norm:
        return 'home_passed'
    # Some KMZ importers flatten one level; still recognise the six HP layer-name variants.
    if hp_key in HOME_PASSED_NAMES:
        return 'home_passed'
    return None

def scan_project(project):
    root = project.layerTreeRoot()
    found = {'pole': [], 'hub_box': [], 'sub_box': [], 'subbox_boundary': [],
             'distribution_cable': [], 'home_passed': [], 'other': []}
    for layer, group_path, layer_name in walk_layer_tree(root):
        category = classify_layer(layer_name, group_path)
        rec = {'layer': layer, 'path': group_path, 'layer_name': layer_name,
               'hub_from_path': next((hub_from_group_name(p) for p in reversed(group_path)
                                      if hub_from_group_name(p)), None)}
        found[category or 'other'].append(rec)
    return found

def summarize_scan(found):
    return {key: len(value) for key, value in found.items()}
