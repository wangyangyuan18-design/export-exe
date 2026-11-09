# -*- coding: utf-8 -*-
"""Name-based classification helpers for the source KMZ/KML tree."""
from .naming import clean_name, norm, hub_from_group_name

HOME_PASSED_NAMES = {'SDU', 'MDU', 'CHURCH', 'COMMERCIAL', 'HOSPITAL', 'INSTITUTION'}
POLE_GROUP_NAMES = {'NEWPOLE', 'EXSITINGPOLE', 'EXISTINGPOLE'}
SUBBOX_POINT_NAMES = {'SUBBOX7030', 'SUBBOX5050', 'ENDBOX'}


def home_passed_key(value):
    """Canonicalise Home Passed folder names and common plural variants."""
    value = norm(value)
    if value == 'CHURCHES':
        return 'CHURCH'
    if value.endswith('S'):
        value = value[:-1]
    return value


def classify_layer(layer_name, group_path=()):
    """Return a semantic category for a KMZ folder/layer name.

    Count suffixes such as ``=14`` are ignored by ``norm``. The folder path is
    used only to distinguish Home Passed folders and pole subfolders.
    """
    leaf = norm(layer_name)
    path_norm = [norm(p) for p in group_path]
    if (any(part in POLE_GROUP_NAMES for part in path_norm)
            or leaf.startswith(('NEWPOLE', 'EXSITINGPOLE', 'EXISTINGPOLE'))):
        return 'pole'
    if leaf == 'HUBBOX' or (leaf.startswith('HUBBOX') and 'BOUNDARY' not in leaf):
        return 'hub_box'
    if 'SUBBOXBOUNDARY' in leaf:
        return 'subbox_boundary'
    if leaf in SUBBOX_POINT_NAMES:
        return 'sub_box'
    if 'DISTRIBUTIONCABLE' in leaf:
        return 'distribution_cable'
    if home_passed_key(layer_name) in HOME_PASSED_NAMES and 'HOMEPASSED' in path_norm:
        return 'home_passed'
    # Accept flattened KML structures where the Home Passed parent was removed.
    if home_passed_key(layer_name) in HOME_PASSED_NAMES:
        return 'home_passed'
    return None


def hub_for_path(path):
    """Return the closest HUB ID embedded in a folder path, if present."""
    for part in reversed(tuple(path or ())):
        value = hub_from_group_name(part)
        if value:
            return value
    return None