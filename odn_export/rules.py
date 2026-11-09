# -*- coding: utf-8 -*-
"""Pure-Python ODN naming and Home Passed value rules (no QGIS dependency)."""
from decimal import Decimal, InvalidOperation

from .naming import clean_name, norm


def numeric_hp_value(raw_value):
    """Convert a KML Placemark Name to numeric HP quantity."""
    raw = str(raw_value or '').strip().replace(',', '').replace('，', '')
    if not raw:
        raise InvalidOperation('empty Name')
    value = Decimal(raw)
    if not value.is_finite():
        raise InvalidOperation('non-finite Name')
    return value


def cable_subbox_target(cable_name, subbox_names):
    """Return the right-most SUB BOX identifier embedded in a DC line name.

    HUB-A assigns the cable to A; A-B assigns it to B. Matching is against the
    full SUB BOX identifier, not a HUB group or nearest spatial feature.
    """
    cable_key = norm(clean_name(cable_name))
    hits = []
    seen = set()
    for subbox_name in subbox_names:
        key = norm(subbox_name)
        if not key or key in seen:
            continue
        seen.add(key)
        position = cable_key.find(key)
        if position >= 0:
            hits.append((position, len(key), subbox_name))
    if not hits:
        return None, []
    hits.sort(key=lambda item: (item[0], item[1]))
    return hits[-1][2], [item[2] for item in hits]