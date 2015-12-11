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

import os
import gzip
import re
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


    def find_icons(self, pkgname, icon_str, icon_sizes):
        return None


    def set_allowed_icon_extensions(self, exts):
        pass


def _decode_contents_line(line):
    try:
        return str(line, 'utf-8')
    except:
        return str(line, 'iso-8859-1')


class ContentsListIconFinder(AbstractIconFinder):
    '''
    An implementation of an IconFinder, using a Contents-<arch>.gz file
    present in Debian archive mirrors to find icons.
    '''

    def __init__(self, suite_name, archive_component, arch_name, archive_mirror_dir):
        self._suite_name = suite_name
        self._component = archive_component
        self._mirror_dir = archive_mirror_dir

        self._icons_data = list()
        self._icon_themes_data = dict()
        self._packages_dict = dict()

        # Preseeded theme names.
        # * allow Oxygen icon theme, needed to support KDE apps (they have no icon at all, otherwise...)
        # * in rare events, GNOME needs the same treatment, so special-case Adwaita as well
        # * We need at least one icon theme to provide the default XDG icon spec stock icons.
        #   A fair take would be to select them between KDE and GNOME at random, but for consistency and
        #   because everyone hates unpredictable behavior, we prefer Adwaita over Oxygen.
        #   (We still see lots of Oxygen icons for software, simply because Oxygen contains more icon sizes,
        #    and often can satisfy an icon requirement much faster)
        self._theme_names = ["Adwaita", "oxygen"]

        self._load_contents_data(arch_name, archive_component)
        # always load the "main" component too, as this holds the icon themes, usually
        self._load_contents_data(arch_name, "main")

        # FIXME: On Ubuntu, also include the universe component to find more icons, since
        # they have split the default iconsets for KDE/GNOME apps between main/universe.
        universe_cfname = os.path.join(self._mirror_dir, "dists", self._suite_name, "universe", "Contents-%s.gz" % (arch_name))
        if os.path.isfile(universe_cfname):
            self._load_contents_data(arch_name, "universe")

    def _load_contents_data(self, arch_name, component):
        contents_basename = "Contents-%s.gz" % (arch_name)
        contents_fname = os.path.join(self._mirror_dir, "dists", self._suite_name, component, contents_basename)

        # Ubuntu does not place the Contents file in a component-specific directory,
        # so fall back to the global one.
        if not os.path.isfile(contents_fname):
            path = os.path.join(self._mirror_dir, "dists", self._suite_name, contents_basename)
            if os.path.isfile(path):
                contents_fname = path

        # load and preprocess the large file.
        # we don't show mercy to memory here, we just want the icon lookup to be fast,
        # so we need to cache the data.
        f = gzip.open(contents_fname, 'r')
        for line in f:
            line = _decode_contents_line(line)
            if line.startswith("usr/share/icons/hicolor/") or line.startswith("usr/share/pixmaps/"):
                self._icons_data.append(line)
                continue

            for theme in self._theme_names:
                if line.startswith("usr/share/icons/"+theme):
                    if not self._icon_themes_data.get(theme):
                        self._icon_themes_data[theme] = list()
                    self._icon_themes_data[theme].append(line)
                    continue

        f.close()

        new_pkgs = read_packages_dict_from_file(self._mirror_dir, self._suite_name, component, arch_name)
        self._packages_dict.update(new_pkgs)

    def _search_icon_in_theme(self, size_str, icon_name, theme_name=None):
        """
        Find icon in the archive contents, in hicolor or in
        a specific theme.
        """

        files_list = list()
        valid = None
        if theme_name:
            if not size_str:
                # we don't search for icons with unknown size in themes
                return None

            # prepare selecting icon from a theme
            files_list = self._icon_themes_data.get(theme_name)
            valid = re.compile('^usr/share/icons/' + theme_name + '/' + size_str + '/.*/' + icon_name + '[\.png|\.svg|\.svgz]')
        else:
            # prepare searching for icon in the global hicolor theme
            files_list = self._icons_data
            if size_str:
                valid = re.compile('^usr/share/icons/.*/' + size_str + '/apps/' + icon_name + '[\.png|\.svg|\.svgz]')
            else:
                valid = re.compile('^usr/share/pixmaps/' + icon_name + '.png')

        # we can't find an icon if the file-list is empty
        if not files_list:
                return None

        res = list()
        for line in files_list:
            if valid.match(line):
                res.append(line)

        for line in res:
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

    def _search_icon(self, size_str, icon_name):
        """
        Find icon files in the archive which match a size.
        """

        # always search for non-theme icon first
        icon = self._search_icon_in_theme(size_str, icon_name)
        if icon:
            return icon

        # then test the themes
        for theme in self._theme_names:
            icon = self._search_icon_in_theme(size_str, icon_name, theme)
            if icon:
                return icon;

        return icon

    def find_icons(self, package, icon, sizes):
        '''
        Tries to find the best possible icon available
        '''
        size_map_flist = dict()

        for size in sizes:
            flist = self._search_icon(str(size), icon)
            if flist:
                size_map_flist[size] = flist

        if not IconSize(64) in size_map_flist:
            # see if we can find a scalable vector graphic as icon
            # we assume "64x64" as size here, and resize the vector
            # graphic later.
            flist = self._search_icon("scalable", icon)

            if flist:
                size_map_flist[IconSize(64)] = flist
            else:
                if IconSize(128) in size_map_flist:
                    # Lots of software doesn't have a 64x64 icon, but a 128x128 icon.
                    # We just implement this small hack to resize the icon to the
                    # appropriate size.
                    size_map_flist[IconSize(64)] = size_map_flist[IconSize(128)]
                else:
                    # some software doesn't store icons in sized XDG directories.
                    # catch these here, and assume that the size is 64x64
                    flist = self._search_icon(None, icon)
                    if flist:
                        size_map_flist[IconSize(64)] = flist

        return size_map_flist


    def set_allowed_icon_extensions(self, exts):
        self._allowed_exts = exts
