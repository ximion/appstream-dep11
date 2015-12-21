#!/usr/bin/env python3
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
import logging as log
from io import StringIO
from configparser import ConfigParser
from dep11.component import IconSize
from dep11.debfile import DebFile
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

    def __init__(self, suite_name, archive_component, arch_name, archive_mirror_dir, icon_theme=None):
        self._suite_name = suite_name
        self._component = archive_component
        self._mirror_dir = archive_mirror_dir

        self._icons_data = list()
        self._theme_data = dict()
        self._packages_dict = dict()

        # Preseeded theme names.
        # * allow Breeze icon theme, needed to support KDE apps (they have no icon at all, otherwise...)
        # * in rare events, GNOME needs the same treatment, so special-case Adwaita as well
        # * We need at least one icon theme to provide the default XDG icon spec stock icons.
        #   A fair take would be to select them between KDE and GNOME at random, but for consistency and
        #   because everyone hates unpredictable behavior, we sort alphabetically and prefer Adwaita over Breeze.
        self._theme_names = ["Adwaita", "breeze"]
        if icon_theme:
            self._theme_names.append(icon_theme)

        self._load_contents_data(arch_name, archive_component)
        # always load the "main" component too, as this holds the icon themes, usually
        self._load_contents_data(arch_name, "main")

        # FIXME: On Ubuntu, also include the universe component to find more icons, since
        # they have split the default iconsets for KDE/GNOME apps between main/universe.
        universe_cfname = os.path.join(self._mirror_dir, "dists", self._suite_name, "universe", "Contents-%s.gz" % (arch_name))
        if os.path.isfile(universe_cfname):
            self._load_contents_data(arch_name, "universe")

        # small optimization: We don't want to look for themes which don't exist
        # on every icon query, so we remove the empty ones.
        for theme in self._theme_names[:]:
            if not self._theme_data.get(theme):
                self._theme_names.remove(theme)
                log.debug("Removing theme '%s' from seeded theme-names: Theme not found." % (theme))
                continue

            # Using multiprocessing, we would reprocess the theme index in every child process when it is needed.
            # this turned out to be more expensive on bigger archives, while it is cheaper on smaller archives where
            # the icon theme doesn't need to be accessed often.
            # In general, it seems to be more desirable to process the theme data once and cache it, even if that means
            # a decrease in performance in case themes aren't needed, since parsing it often in subprocesses is always
            # a lot more expensive.
            if not self._theme_data[theme].get('icons'):
                    self._theme_data[theme]['icons'] = self._load_theme_index(theme, self._theme_data[theme]['pkg'])
            theme_icons = self._theme_data[theme]['icons']
            if not theme_icons:
                log.error("Removing seeded theme: '%s'" % (theme))
                self._theme_names.remove(theme)


    def _load_contents_data(self, arch_name, component):
        contents_basename = "Contents-%s.gz" % (arch_name)
        contents_fname = os.path.join(self._mirror_dir, "dists", self._suite_name, component, contents_basename)

        # Ubuntu does not place the Contents file in a component-specific directory,
        # so fall back to the global one.
        if not os.path.isfile(contents_fname):
            path = os.path.join(self._mirror_dir, "dists", self._suite_name, contents_basename)
            if os.path.isfile(path):
                contents_fname = path

        # we need information about the whole package, not only the package-name,
        # otherwise icon-theme support won't work and we also don't know where the
        # actual .deb files are stored.
        new_pkgs = read_packages_dict_from_file(self._mirror_dir, self._suite_name, component, arch_name)
        self._packages_dict.update(new_pkgs)

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
                if self._theme_data.get(theme):
                    continue
                if line.startswith(os.path.join("usr/share/icons/", theme, "index.theme")):
                    fname, pkg = self._file_pkg_from_contents_line(line)
                    if not pkg:
                        continue

                    self._theme_data[theme] = dict()
                    pkg['filename'] = os.path.join(self._mirror_dir, pkg['filename'])
                    self._theme_data[theme]['pkg'] = pkg

        f.close()


    def _file_pkg_from_contents_line(self, raw_line):
        line = raw_line.strip(' \t\n\r')
        if not " " in line:
            return None
        parts = line.split(" ", 1)
        path = parts[0].strip()
        group_pkg = parts[1].strip()
        if "/" in group_pkg:
            pkgname = group_pkg.split("/", 1)[1].strip()
        else:
            pkgname = group_pkg
        return (path, self._packages_dict.get(pkgname))


    def _load_theme_index(self, theme_name, theme_pkg):
        """
        Preprocess information from an XDG icon theme file
        """

        try:
            deb = DebFile(theme_pkg['filename'])
        except Exception as e:
            log.error("Error reading icon-theme deb file '%s': %s" % (theme_pkg['filename'], e))
            return None

        try:
            filelist = deb.get_filelist()
        except Exception as e:
            log.error("List of files for icon-theme '%s' could not be read" % (theme_pkg['filename']))
            filelist = None

        tf = ConfigParser(allow_no_value=True, interpolation=None)
        try:
            indexdata = deb.get_file_data(os.path.join("usr/share/icons", theme_name, "index.theme"))
            indexdata = str(indexdata, 'utf-8')
            tf.readfp(StringIO(indexdata))
        except Exception as e:
            log.error("Unable to read theme index of icon-theme '%s': %s" % (theme_pkg['filename'], str(e)))
            return None

        icon_info = dict()
        icon_info['files'] = set(filelist)
        def evaluate_size(size, real_size, section):
            if size != 'scalable':
                if real_size < size:
                    # we don't do upscaling of images
                    return
            if not icon_info.get(size):
                icon_info[size] = dict()

            old_real_size = icon_info[size].get('real_size')
            if not old_real_size:
                old_real_size = 0
            if old_real_size == size:
                # we already have our perfect size
                return
            if old_real_size < real_size:
                icon_info[size]['section'] = section
                icon_info[size]['real_size'] = real_size

        for sec in tf.sections():
            try:
                context = tf.get(sec, "Context")
                tp = tf.get(sec, "Type")
                size = tf.get(sec, "Size")
            except:
                continue
            if not context or not size:
                continue
            if context.lower() != "applications":
                continue
            try:
                size = int(size)
            except ValueError:
                continue

            if tp.lower() == "fixed":
                evaluate_size(64, size, sec)
                evaluate_size(128, size, sec)
            elif tp.lower() == "scalable":
                evaluate_size('scalable', size, sec)

        return icon_info


    def _search_icon_in_theme(self, size, icon_name, theme_name=None):
        """
        Find icon in the archive contents, in hicolor or in
        a specific theme.
        """

        files_list = list()
        valid = None
        if theme_name:
            if not size:
                # we don't search for icons with unknown size in themes
                return None

            theme_icons = self._theme_data[theme_name]['icons']
            if not theme_icons:
                return None

            files_list = theme_icons['files']
            if not files_list:
                # no file-list: This could mean other keys in the
                # theme_icons dict aren't set as well, so we shouldn't
                # continue here.
                # Also, without icons, there's nothing to do for us anyway.
                return None

            info = None
            if size == 'scalable':
                info = theme_icons.get('scalable')
            else:
                info = theme_icons.get(int(size))
            if not info:
                return None

            # prepare selecting icon from a theme
            icon_fname_noext = "usr/share/icons/" + theme_name + "/" + info['section'] + "/" + icon_name
            for ext in (".png", ".svg", ".svgz"):
                icon_fname = icon_fname_noext+ext
                if icon_fname in files_list:
                    # for themes we already stored the absolute .deb file path, no need to os.path.join it
                    deb_fname = self._theme_data[theme_name]['pkg']['filename']
                    return {'icon_fname': icon_fname, 'deb_fname': deb_fname}

        else:
            size_str = str(size)
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
                fname, pkg = self._file_pkg_from_contents_line(line)
                if not pkg:
                    continue

                deb_fname = os.path.join(self._mirror_dir, pkg['filename'])
                return {'icon_fname': fname, 'deb_fname': deb_fname}

        return None

    def _search_icon(self, size, icon_name):
        """
        Find icon files in the archive which match a size.
        """

        # always search for icon in hicolor theme or in non-theme locations first
        icon = self._search_icon_in_theme(size, icon_name)
        if icon:
            return icon

        # then test the themes
        for theme in self._theme_names:
            icon = self._search_icon_in_theme(size, icon_name, theme)
            if icon:
                return icon;

        return icon

    def find_icons(self, package, icon, sizes):
        '''
        Tries to find the best possible icon available
        '''
        size_map_flist = dict()

        for size in sizes:
            flist = self._search_icon(size, icon)
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
