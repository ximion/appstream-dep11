#!/usr/bin/env python
#
# Copyright (c) 2015 Matthias Klumpp <mak@debian.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3.0 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program.

import os
import yaml
import logging as log

from dep11.utils import get_data_dir

__all__ = []

_DEP11_HINT_DESCRIPTIONS = None

class HintSeverity:
    '''
    Importance of a component parsing hint.
    '''
    ERROR = 3
    WARNING = 2
    INFO = 1

__all__.append('HintSeverity')


class Hint:
    '''
    An issue found with the metadata.
    '''
    severity = HintSeverity.INFO
    tag_name = str()
    text_params = dict()

    def __init__(self, severity, tag, params):
        self.severity = severity
        self.tag_name = tag
        self.text_params = params

    def __str__(self):
        return "%s: %s (%s)" % (str(self.severity), tag_name, str(text_params))

__all__.append('Hint')


def get_hints_index_fname():
    '''
    Find the YAML tag description, even if the DEP-11 metadata generator
    is not properly installed.
    '''
    fname = os.path.join(get_data_dir(), "dep11-hints.yml")
    if os.path.isfile(fname):
        return fname

    raise Exception("Could not find tag description file (dep11-hints.yml).")


def get_hint_description_index():
    global _DEP11_HINT_DESCRIPTIONS
    if not _DEP11_HINT_DESCRIPTIONS:
        fname = get_hints_index_fname()
        f = open(fname, 'r')
        _DEP11_HINT_DESCRIPTIONS = yaml.safe_load(f.read())
        f.close()
    return _DEP11_HINT_DESCRIPTIONS

__all__.append('get_hint_description_index')


def get_hint_tag_info(tag_name):
    idx = get_hint_description_index()
    tag = idx.get(tag_name)
    if not tag:
        log.error("Could not find tag name: %s", tag_name)
        tag = idx.get("internal-unknown-tag")
    return tag

__all__.append('get_hint_tag_info')


def get_hint_severity(tag_name):
    tag = get_hint_tag_info(tag_name)
    severity = tag.get('severity')
    if not severity:
        log.error("Tag %s has no severity!", tag_name)
    if severity == "warning":
        return HintSeverity.WARNING
    if severity == "info":
        return HintSeverity.INFO
    return HintSeverity.ERROR

__all__.append('get_hint_severity')


def hint_tag_is_internal(tag_name):
    tag = get_hint_tag_info(tag_name)
    internal = tag.get('internal')
    if internal:
        return True
    return False

__all__.append('hint_tag_is_internal')


def hint_tag_is_error(tag_name):
    tag = get_hint_tag_info(tag_name)
    severity = tag.get('severity')
    if not severity:
        log.error("Tag %s has no severity!", tag_name)
    if severity == "error":
        return True
    return False

__all__.append('hint_tag_is_error')
