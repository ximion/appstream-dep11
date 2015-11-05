#!/usr/bin/env python3
#
# Copyright (C) 2014-2015 Matthias Klumpp <mak@debian.org>
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
import logging as log
from kyotocabinet import *


class DataCache:
    """ A KyotoCabinet based cache for the DEP-11 generator """

    def __init__(self, media_dir):
        self._pkgdb = DB()
        self._hintsdb = DB()
        self._datadb = DB()
        self._opened = False
        self.media_dir = media_dir

    def open(self, cachedir):
        if not self._pkgdb.open(os.path.join(cachedir, "packages.kch"), DB.OREADER | DB.OWRITER | DB.OCREATE):
            log.error("Could not open cache: %s" % (str(self._db.error())), file=sys.stderr)
            return False

        if not self._hintsdb.open(os.path.join(cachedir, "hints.kch"), DB.OREADER | DB.OWRITER | DB.OCREATE):
            log.error("Could not open cache: %s" % (str(self._db.error())), file=sys.stderr)
            return False

        if not self._datadb.open(os.path.join(cachedir, "metadata.kch"), DB.OREADER | DB.OWRITER | DB.OCREATE):
            log.error("Could not open cache: %s" % (str(self._db.error())), file=sys.stderr)
            return False
        return True

    def begin_transaction(self):
        self._pkgdb.begin_transaction()
        self._hintsdb.begin_transaction()
        self._datadb.begin_transaction()

    def end_transaction(self):
        self._pkgdb.end_transaction()
        self._hintsdb.end_transaction()
        self._datadb.end_transaction()

    def has_metadata(self, checksum):
        return self._datadb.get_str(checksum) != None

    def get_metadata(self, pkgid):
        cs_str = self._pkgdb.get_str(pkgid)
        if not cs_str:
            return None
        if cs_str == "ignore":
            return None
        csl = cs_str.split("\n")

        data = ""
        for cs in csl:
            d = self._datadb.get_str(cs)
            if d:
                data += d
        return data

    def set_package_ignore(self, pkgid):
        self._pkgdb.set(pkgid, "ignore")

    def set_components(self, pkgid, cpts):
        # if the package has no components,
        # mark it as always-ignore
        if len(cpts) == 0:
            self._pkgdb.set(pkgid, "ignore")
            return

        checksums = list()
        hints_str = ""
        for cpt in cpts:
            # get the metadata in YAML format
            md_yaml = cpt.to_yaml_doc()
            if not cpt.has_ignore_reason():
                self._datadb.set(cpt.srcdata_checksum, md_yaml)
                checksums.append(cpt.srcdata_checksum)
            hints_yml = cpt.get_hints_yaml()
            if hints_yml:
                hints_str += hints_yml

        self.set_hints(pkgid, hints_str)
        if checksums:
            self._pkgdb.set(pkgid, "\n".join(checksums))

    def get_hints(self, pkgid):
        return self._hintsdb.get_str(pkgid)

    def set_hints(self, pkgid, hints_yml):
        self._hintsdb.set(pkgid, hints_yml)

    def remove_package(self, pkgid):
        self._pkgdb.remove(pkgid)
        self._hintsdb.remove(pkgid)

    def is_ignored(self, pkgid):
        return self._pkgdb.get_str(pkgid) == "ignore"

    def package_exists(self, pkgid):
        return self._pkgdb.get_str(pkgid) != None
