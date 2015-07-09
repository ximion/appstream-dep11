#!/usr/bin/env python
#
# Copyright (c) 2014-2015 Matthias Klumpp <mak@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os
from subprocess import check_output
from dep11.component import IconSize
from dep11.utils import read_packages_dict_from_file

class AbstractIconFinder:
    '''
    An icon-finder finds an icon in the archive, if it has not yet
    been found in the analyzed package already.
    AbstractIconFinder is a dummy class, not implementing the
    methods needed to find an icon.
    '''

    def __init__(self, suite_name, archive_component):
        pass

    def find_icons(self, pkgname, icon_str, icon_sizes, binid=-1):
        return None

    def set_allowed_icon_extensions(self, exts):
        pass


class ZGrepIconFinder(AbstractIconFinder):
    '''
    An implementation of an IconFinder, using zgrep on a Contents-<arch>.gz file
    present in Debian archive mirrors.
    '''

    def __init__(self, suite_name, archive_component, arch_name, archive_mirror_dir, pkgdict=None):
        self._suite_name = suite_name
        self._component = archive_component

        self._mirror_dir = archive_mirror_dir
        contents_fname = "Contents-%s.gz" % (arch_name)
        self._contents_file = os.path.join(archive_mirror_dir, "dists", suite_name, archive_component, contents_fname)

        self._packages_dict = pkgdict
        if not self._packages_dict:
            self._packages_dict = read_packages_dict_from_file(archive_mirror_dir, suite_name, archive_component, arch_name)

    def _query_icon(self, size, icon):
        '''
        Find icon files in the archive which match a size.
        '''

        if not os.path.isfile(self._contents_file):
            return None

        search_param = None
        if size:
            search_param = '^usr/share/icons/hicolor/' + size + '/.*' + icon + '[\.png|\.svg|\.svgz]'
        else:
            search_param = '^usr/share/pixmaps/' + icon + '.png'

        res = None
        try:
            res = check_output(["zgrep", "-i", search_param, self._contents_file], universal_newlines=True)
            res = str(res)
        except Exception as e:
            # we silently ignore errors. Not good, but at time we have no way to report them.
            # TODO: Log this to the logfile
            return None

        for line in res.split('\n'):
            line = line.strip(' \t\n\r')
            if not " " in line:
                continue
            parts = line.split(" ", 1)
            path = parts[0].strip()
            group_pkg = parts[1].strip()
            if not "/" in group_pkg:
                continue
            pkgname = group_pkg.split("/", 1)[1].strip()

            pkg = self._packages_dict.get(pkgname)
            if not pkg:
                continue

            deb_fname = os.path.join(self._mirror_dir, pkg['filename'])
            return {'icon_fname': path, 'deb_fname': deb_fname}

        return None

    def find_icons(self, package, icon, sizes, binid):
        '''
        Tries to find the best possible icon available
        '''
        size_map_flist = dict()

        for size in sizes:
            flist = self._query_icon(str(size), icon)
            if flist:
                size_map_flist[size] = flist

        if not IconSize(64) in size_map_flist:
            # see if we can find a scalable vector graphic as icon
            # we assume "64x64" as size here, and resize the vector
            # graphic later.
            flist = self._query_icon("scalable", icon)
            if flist:
                size_map_flist[IconSize(64)] = flist
            else:
                # some software doesn't store icons in sized XDG directories.
                # catch these here, and assume that the size is 64x64
                flist = self._query_icon(None, icon)
                if flist:
                    size_map_flist[IconSize(64)] = flist

        return size_map_flist

    def set_allowed_icon_extensions(self, exts):
        self._allowed_exts = exts
