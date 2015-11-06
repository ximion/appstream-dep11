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
import glob
import shutil
import logging as log
import lmdb
from math import pow


def tobytes(s):
    if isinstance(s, bytes):
        return s
    return bytes(s, 'utf-8')

class DataCache:
    """ A LMDB based cache for the DEP-11 generator """

    def __init__(self, media_dir):
        self._pkgdb = None
        self._hintsdb = None
        self._datadb = None
        self._dbenv = None
        self.cache_dir = None
        self._opened = False

        self.media_dir = media_dir

        # set a huge map size to be futureproof.
        # This means we're cruel to non-64bit users, but this
        # software is supposed to be run on 64bit machines anyway.
        self._map_size = pow(1024, 4)

    def open(self, cachedir):
        self._dbenv = lmdb.open(cachedir, max_dbs=3, map_size=self._map_size)

        self._pkgdb = self._dbenv.open_db(b'packages')
        self._hintsdb = self._dbenv.open_db(b'hints')
        self._datadb = self._dbenv.open_db(b'metadata')

        self._opened = True
        self.cache_dir = cachedir
        return True

    def close(self):
        if not self._opened:
            return
        self._dbenv.close()

        self._pkgdb = None
        self._hintsdb = None
        self._datadb = None
        self._dbenv = None
        self._opened = False

    def reopen(self):
        self.close()
        self.open(self.cache_dir)

    def metadata_exists(self, global_id):
        gid = tobytes(global_id)
        with self._dbenv.begin(db=self._datadb) as txn:
            return txn.get(gid) != None

    def get_metadata(self, global_id):
        gid = tobytes(global_id)
        with self._dbenv.begin(db=self._datadb) as dtxn:
                d = dtxn.get(tobytes(gid))
                if not d:
                    return None
                return str(d, 'utf-8')

    def set_metadata(self, global_id, yaml_data):
        gid = tobytes(global_id)
        with self._dbenv.begin(db=self._datadb, write=True) as txn:
            txn.put(gid, tobytes(yaml_data))

    def set_package_ignore(self, pkgid):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._pkgdb, write=True) as txn:
            txn.put(pkgid, b'ignore')

    def get_cpt_gids_for_pkg(self, pkgid):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._pkgdb) as txn:
            cs_str = txn.get(pkgid)
            if not cs_str:
                return None
            cs_str = str(cs_str, 'utf-8')
            if cs_str == 'ignore' or cs_str == 'seen':
                return None
            gids = cs_str.split("\n")
            return gids

    def get_metadata_for_pkg(self, pkgid):
        gids = self.get_cpt_gids_for_pkg(pkgid)
        if not gids:
            return None

        data = ""
        for gid in gids:
            d = self.get_metadata(gid)
            if d:
                data += d
        return data

    def set_components(self, pkgid, cpts):
        # if the package has no components,
        # mark it as always-ignore
        if len(cpts) == 0:
            self.set_package_ignore(pkgid)
            return

        pkgid = tobytes(pkgid)

        gids = list()
        hints_str = ""
        for cpt in cpts:
            # check for ignore-reasons first, to avoid a database query
            if not cpt.has_ignore_reason():
                if self.metadata_exists(cpt.global_id):
                    gids.append(cpt.global_id)
                else:
                    # get the metadata in YAML format
                    md_yaml = cpt.to_yaml_doc()
                    # we need to check for ignore reasons again, since generating
                    # the YAML doc may have raised more errors
                    if not cpt.has_ignore_reason():
                        self.set_metadata(cpt.global_id, md_yaml)
                        gids.append(cpt.global_id)

            hints_yml = cpt.get_hints_yaml()
            if hints_yml:
                hints_str += hints_yml

        self.set_hints(pkgid, hints_str)
        if gids:
            with self._dbenv.begin(db=self._pkgdb, write=True) as txn:
                txn.put(pkgid, bytes("\n".join(gids), 'utf-8'))
        elif hints_str:
            # we need to set some value for this package, to show that we've seen it
            with self._dbenv.begin(db=self._pkgdb, write=True) as txn:
                txn.put(pkgid, b'seen')

    def get_hints(self, pkgid):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._hintsdb) as txn:
            hints = txn.get(pkgid)
            if hints:
                hints = str(hints, 'utf-8')
            return hints

    def set_hints(self, pkgid, hints_yml):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._hintsdb, write=True) as txn:
            txn.put(pkgid, tobytes(hints_yml))

    def _cleanup_empty_dirs(self, d):
        parent = os.path.abspath(os.path.join(d, os.pardir))
        if not os.path.isdir(parent):
            return
        if not os.listdir(parent):
            os.rmdir(parent)
        parent = os.path.abspath(os.path.join(parent, os.pardir))
        if not os.path.isdir(parent):
            return
        if not os.listdir(parent):
            os.rmdir(parent)

    def remove_package(self, pkgid):
        log.debug("Dropping package: %s" % (pkgid))
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._pkgdb, write=True) as pktxn:
            pktxn.delete(pkgid)
        with self._dbenv.begin(db=self._hintsdb, write=True) as htxn:
            htxn.delete(pkgid)

    def is_ignored(self, pkgid):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._pkgdb) as txn:
            return txn.get(pkgid) == b'ignore'

    def package_exists(self, pkgid):
        pkgid = tobytes(pkgid)
        with self._dbenv.begin(db=self._pkgdb) as txn:
            return txn.get(pkgid) != None

    def get_packages_not_in_set(self, pkgset):
        res = set()
        if not pkgset:
            pkgset = set()
        with self._dbenv.begin(db=self._pkgdb) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if not str(key, 'utf-8') in pkgset:
                    res.add(key)
        return res

    def remove_orphaned_components(self):
        gid_pkg = dict()

        with self._dbenv.begin(db=self._pkgdb) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if not value or value == b'ignore' or value == b'seen':
                    continue
                value = str(value, 'utf-8')
                gids = value.split("\n")
                for gid in gids:
                    if not gid_pkg.get(gid):
                        gid_pkg[gid] = list()
                    gid_pkg[gid].append(key)

        # remove the media and component data, if component is orphaned
        with self._dbenv.begin(db=self._datadb) as dtxn:
            cursor = dtxn.cursor()
            for gid, yaml in cursor:
                gid = str(gid, 'utf-8')

                # Check if we have a package which is still referencing this component
                pkgs = gid_pkg.get(gid)
                if pkgs:
                    continue

                # drop cached media
                dirs = glob.glob(os.path.join(self.media_dir, "*", gid))
                if dirs:
                    shutil.rmtree(dirs[0])
                    log.info("Expired media: %s" % (gid))
                    # remove possibly empty directories
                    self._cleanup_empty_dirs(dirs[0])

                # drop component from db
                with self._dbenv.begin(db=self._datadb, write=True) as dtxn:
                    dtxn.delete(tobytes(gid))
