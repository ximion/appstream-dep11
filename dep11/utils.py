#!/usr/bin/env python3
#
# Copyright (c) 2014-2016 Matthias Klumpp <mak@debian.org>
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
import sys
import yaml


def str_enc_dec(val):
    '''
    Handles encoding decoding for localized values.
    '''

    if isinstance(val, str):
        val = bytes(val, 'utf-8')
    val = val.decode("utf-8", "replace")

    return val

def build_pkg_id(name, version, arch):
    return "%s/%s/%s" % (name, version, arch)

def build_cpt_global_id(cptid, checksum, allow_no_checksum=False):
    if not cptid:
        return None
    if not allow_no_checksum and not checksum:
        return None

    gid = None
    parts = None
    if cptid.startswith(("org.", "net.", "com.", "io.", "edu.", "name.")):
        parts = cptid.split(".", 2)
    if parts and len(parts) > 2:
        gid = "%s/%s/%s/%s" % (parts[0].lower(), parts[1], parts[2], checksum)
    else:
        gid = "%s/%s/%s/%s" % (cptid[0].lower(), cptid[:2].lower(), cptid, checksum)

    return gid

def get_data_dir():
    """Return data directory path. Check first in master, then virtualenv or installed system version."""

    dep11_dir = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(os.path.dirname(dep11_dir), "data")
    if os.path.isdir(data_dir):
        return data_dir

    return os.path.join(sys.prefix, "share", "dep11")

def load_generator_config(wdir):
    conf_fname = os.path.join(wdir, "dep11-config.yml")
    if not os.path.isfile(conf_fname):
        print("Could not find configuration! Make sure 'dep11-config.yml' exists!")
        return None

    f = open(conf_fname, 'r')
    conf = yaml.safe_load(f.read())
    f.close()

    if not conf:
        print("Configuration is empty!")
        return None

    if not conf.get("ArchiveRoot"):
        print("You need to specify an archive root path.")
        return None

    if not conf.get("Suites"):
        print("Config is missing information about suites!")
        return None

    if not conf.get("MediaBaseUrl"):
        print("You need to specify an URL where additional data (like screenshots) can be downloaded.")
        return None

    return conf
