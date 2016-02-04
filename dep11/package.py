#!/usr/bin/env python3
#
# Copyright (c) 2016 Matthias Klumpp <mak@debian.org>
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
import gzip
from .debfile import DebFile
from apt_pkg import TagFile, version_compare


class Package:
    name = None
    version = None
    arch = None
    maintainer = None
    description = dict()

    def __init__(self, name, version, arch, fname=None):
        self.name = name
        self.version = version
        self.arch = arch
        self.filename = fname

        self._debfile = None


    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, val):
        self._filename = val
        self._debfile = None

    @property
    def debfile(self):
        if self._debfile:
            return self._debfile
        if not self.filename:
            return None
        self._debfile = DebFile(self.filename)
        return self._debfile

    @property
    def pkid(self):
        return "%s/%s/%s" % (self.name, self.version, self.arch)


    def set_description(self, locale, desc):
        description[locale] = desc


    def has_description(self):
        return True if description else False


def read_packages_dict_from_file(archive_root, suite, component, arch):
    source_path = archive_root + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, component, arch)

    f = gzip.open(source_path, 'rb')
    tagf = TagFile(f)
    package_dict = dict()
    for section in tagf:
        pkg = Package(section['Package'], section['Version'], section['Architecture'])
        if not section.get('Filename'):
            print("Package %s-%s has no filename specified." % (pkg['name'], pkg['version']))
            continue
        pkg.filename = section['Filename']
        pkg.maintainer = section['Maintainer']

        pkg2 = package_dict.get(pkg.name)
        if pkg2:
            compare = version_compare(pkg2.version, pkg.version)
            if compare >= 0:
                continue
        package_dict[pkg.name] = pkg

    return package_dict
