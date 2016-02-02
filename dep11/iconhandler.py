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


def _decode_contents_line(line):
    try:
        return str(line, 'utf-8')
    except:
        return str(line, 'iso-8859-1')


class Theme:
    def __init__(self, name, deb_fname):
        self.name = name
        self.directories = list()

        deb = DebFile(deb_fname)
        indexdata = str(deb.get_file_data(os.path.join('usr/share/icons', name, 'index.theme')), 'utf-8')

        index = ConfigParser(allow_no_value=True, interpolation=None)
        index.optionxform = str   # don't lower-case option names
        index.readfp(StringIO(indexdata))

        for section in index.sections():
            size = index.getint(section, 'Size', fallback=None)
            context = index.get(section, 'Context', fallback=None)
            if not size:
                continue

            themedir = {
                'path': section,
                'type': index.get(section, 'Type', fallback='Threshold'),
                'size': size,
                'minsize': index.getint(section, 'MinSize', fallback=size),
                'maxsize': index.getint(section, 'MaxSize', fallback=size),
                'threshold': index.getint(section, 'Threshold', fallback=2)
            }

            self.directories.append(themedir)


    def _directory_matches_size(self, themedir, size):
        if themedir['type'] == 'Fixed':
            return size == themedir['size']
        elif themedir['type'] == 'Scalable':
            return themedir['minsize'] <= size <= themedir['maxsize']
        elif themedir['type'] == 'Threshold':
            return size - themedir['threshold'] <= size <= size + themedir['threshold']


    def matching_icon_filenames(self, name, size):
        '''
        Returns an iteratable of possible icon filenames that match 'name' and 'size'.
        '''
        for themedir in self.directories:
            if self._directory_matches_size(themedir, size):
                for extension in ('png', 'svg', 'svgz', 'xpm'):
                    yield 'usr/share/icons/{}/{}/{}.{}'.format(self.name, themedir['path'], name, extension)


class ContentsListIconFinder(AbstractIconFinder):
    '''
    An implementation of an IconFinder, using a Contents-<arch>.gz file
    present in Debian archive mirrors to find icons.
    '''

    def __init__(self, suite_name, archive_component, arch_name, archive_mirror_dir, icon_theme=None, base_suite_name=None):
        self._component = archive_component
        self._mirror_dir = archive_mirror_dir

        self._packages = dict()
        self._themes = list()
        self._icon_files = dict()

        # Preseeded theme names.
        # * prioritize hicolor, because that's where apps often install their upstream icon
        # * then look at the theme given in the config file
        # * allow Breeze icon theme, needed to support KDE apps (they have no icon at all, otherwise...)
        # * in rare events, GNOME needs the same treatment, so special-case Adwaita as well
        # * We need at least one icon theme to provide the default XDG icon spec stock icons.
        #   A fair take would be to select them between KDE and GNOME at random, but for consistency and
        #   because everyone hates unpredictable behavior, we sort alphabetically and prefer Adwaita over Breeze.
        self._theme_names = ['hicolor']
        if icon_theme:
            self._theme_names.append(icon_theme)
        self._theme_names.extend(['Adwaita', 'breeze'])

        # load the 'main' component of the base suite, in case the given suite depends on it
        if base_suite_name:
            self._load_contents_data(arch_name, base_suite_name, 'main')

        self._load_contents_data(arch_name, suite_name, archive_component)
        # always load the "main" component too, as this holds the icon themes, usually
        self._load_contents_data(arch_name, suite_name, "main")

        # FIXME: On Ubuntu, also include the universe component to find more icons, since
        # they have split the default iconsets for KDE/GNOME apps between main/universe.
        universe_cfname = os.path.join(self._mirror_dir, "dists", suite_name, "universe", "Contents-%s.gz" % (arch_name))
        if os.path.isfile(universe_cfname):
            self._load_contents_data(arch_name, suite_name, "universe")

        loaded_themes = set(theme.name for theme in self._themes)
        missing = set(self._theme_names) - loaded_themes
        for theme in missing:
            log.info("Removing theme '%s' from seeded theme-names: Theme not found." % (theme))


    def _load_contents_data(self, arch_name, suite_name, component):
        contents_basename = "Contents-%s.gz" % (arch_name)
        contents_fname = os.path.join(self._mirror_dir, "dists", suite_name, component, contents_basename)

        # Ubuntu does not place the Contents file in a component-specific directory,
        # so fall back to the global one.
        if not os.path.isfile(contents_fname):
            path = os.path.join(self._mirror_dir, "dists", suite_name, contents_basename)
            if os.path.isfile(path):
                contents_fname = path

        # we need information about the whole package, not only the package-name,
        # otherwise icon-theme support won't work and we also don't know where the
        # actual .deb files are stored.
        for name, pkg in read_packages_dict_from_file(self._mirror_dir, suite_name, component, arch_name).items():
            pkg['filename'] = os.path.join(self._mirror_dir, pkg['filename'])
            self._packages[name] = pkg

        # load and preprocess the large file.
        # we don't show mercy to memory here, we just want the icon lookup to be fast,
        # so we need to cache the data.
        with gzip.open(contents_fname, 'r') as f:
            for line in f:
                line = _decode_contents_line(line)
                fname, pkg = self._file_pkg_from_contents_line(line)
                if not pkg:
                    continue

                if fname.startswith('usr/share/pixmaps/'):
                    self._icon_files[fname] = pkg
                    continue

                for name in self._theme_names:
                    if fname == 'usr/share/icons/{}/index.theme'.format(name):
                        self._themes.append(Theme(name, pkg['filename']))
                    elif fname.startswith('usr/share/icons/{}'.format(name)):
                        self._icon_files[fname] = pkg


    def _file_pkg_from_contents_line(self, raw_line):
        line = raw_line.strip(' \t\n\r')
        if not " " in line:
            return (None, None)
        parts = line.split(" ", 1)
        path = parts[0].strip()
        group_pkg = parts[1].strip()
        if "/" in group_pkg:
            pkgname = group_pkg.split("/", 1)[1].strip()
        else:
            pkgname = group_pkg
        return (path, self._packages.get(pkgname))


    def _possible_icon_filenames(self, icon, size):
        for theme in self._themes:
            for fname in theme.matching_icon_filenames(icon, size):
                yield fname

        for extension in ('.png', '.svg', '.xpm', '.gif', '.svgz', '.jpg'):
            yield 'usr/share/pixmaps/{}.{}'.format(icon, extension)


    def find_icons(self, package, icon, sizes):
        '''
        Looks up 'icon' with 'size' in popular icon themes according to the XDG
        icon theme spec.
        '''
        size_map_flist = dict()

        for size in sizes:
            for fname in self._possible_icon_filenames(icon, size):
                pkg = self._icon_files.get(fname)
                if pkg:
                    size_map_flist[size] = { 'icon_fname': fname, 'deb_fname': pkg['filename'] }

        return size_map_flist
