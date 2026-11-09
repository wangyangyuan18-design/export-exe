# -*- coding: utf-8 -*-
"""Discover semantic layers and group paths in a QGIS project loaded from KMZ."""
from .naming import clean_name, norm, hub_from_group_name

HOME_PASSED_NAMES = {'sdus', 'mdus', 'church', 'commercial', 'hospitals', 'institution'}
POLE_GROUP_NAMES = {'newpole', 'exsitingpole', 'existingpole'}
SUBBOX_POINT_NAMES = {'subbox7030', 'subbox5050', 'endbox'}

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
    if _has_pole_ancestor(group_path):
        return 'pole'
    if leaf == 'hubbox' or (leaf.startswith('hubbox') and 'boundary' not in leaf):
        return 'hub_box'
    if 'subboxboundary' in leaf:
        return 'subbox_boundary'
    if leaf in SUBBOX_POINT_NAMES:
        return 'sub_box'
    if 'distributioncable' in leaf:
        return 'distribution_cable'
    if leaf in HOME_PASSED_NAMES and 'homepassed' in path_norm:
        return 'home_passed'
    # Some KMZ importers flatten one level; still recognize the six exact HP layer names.
    if leaf in HOME_PASSED_NAMES:
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
