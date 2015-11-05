#!/usr/bin/env python
#
# Copyright (c) 2014-2015 Matthias Klumpp <mak@debian.org>
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

import gzip
from apt_pkg import TagFile, version_compare

def str_enc_dec(val):
    '''
    Handles encoding decoding for localized values.
    '''

    if isinstance(val, str):
        val = bytes(val, 'utf-8')
    val = val.decode("utf-8", "replace")

    return val

def read_packages_dict_from_file(archive_root, suite, component, arch):
    source_path = archive_root + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, component, arch)

    f = gzip.open(source_path, 'rb')
    tagf = TagFile(f)
    package_dict = dict()
    for section in tagf:
        pkg = dict()
        pkg['arch'] = section['Architecture']
        pkg['version'] = section['Version']
        pkg['name'] = section['Package']
        if not section.get('Filename'):
            print("Package %s-%s has no filename specified." % (pkg['name'], pkg['version']))
            continue
        pkg['filename'] = section['Filename']
        pkg['maintainer'] = section['Maintainer']

        pkg2 = package_dict.get(pkg['name'])
        if pkg2:
            compare = version_compare(pkg2['version'], pkg['version'])
            if compare >= 0:
                continue
        package_dict[pkg['name']] = pkg

    return package_dict

def build_cpt_global_id(cptid, checksum):
    if (not checksum) or (not cptid):
        return None

    gid = None
    parts = None
    if cptid.startswith(("org.", "net.", "com.", "io.")):
        parts = cptid.split(".", 2)
    if parts and len(parts) > 2:
        gid = "%s/%s/%s/%s" % (parts[0].lower(), parts[1], parts[2], checksum)
    else:
        gid = "%s/%s/%s" % (cptid[0].lower(), cptid, checksum)

    return gid
