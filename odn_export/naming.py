# -*- coding: utf-8 -*-
import re

_COUNT_SUFFIX_RE = re.compile(r'\s*=\s*\d+\s*$')
_SUBBOX_RE = re.compile(r'^(?P<hub>.+?HB\d+)L(?P<link>\d+)S(?P<seq>\d+)$', re.IGNORECASE)
_HUB_RE = re.compile(r'(?P<hub>[A-Z0-9_-]*?HB\d+)', re.IGNORECASE)

def strip_count_suffix(value):
    """Strip only a trailing '=number' count from KMZ group/layer names."""
    return _COUNT_SUFFIX_RE.sub('', str(value or '').strip()).strip()

def clean_name(value):
    return strip_count_suffix(value).strip()

def norm(value):
    return ''.join(ch.upper() for ch in clean_name(value) if ch.isalnum())

def parse_subbox_name(value):
    cleaned = clean_name(value)
    match = _SUBBOX_RE.match(cleaned)
    if not match:
        return None
    return match.group('hub').upper(), int(match.group('link')), int(match.group('seq'))

def hub_from_group_name(value):
    cleaned = clean_name(value)
    match = _HUB_RE.search(cleaned)
    return match.group('hub').upper() if match else None

def natural_hub_key(value):
    value = clean_name(value).upper()
    match = re.match(r'^(.*?HB)(\d+)$', value)
    if match:
        return (match.group(1), int(match.group(2)), value)
    return (value, -1, value)

def subbox_sort_key(value):
    parsed = parse_subbox_name(value)
    if not parsed:
        return (("~", 999999, str(value).upper()), 999999, 999999, str(value).upper())
    hub, link, seq = parsed
    return (natural_hub_key(hub), link, seq, str(value).upper())
