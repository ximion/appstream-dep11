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
import gzip
import logging as log

from .package import read_packages_dict_from_file


__all__ = list()

def _decode_contents_line(line):
    try:
        return str(line, 'utf-8')
    except:
        return str(line, 'iso-8859-1')


def _file_pkg_from_contents_line(raw_line):
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
    return path, pkgname


def parse_contents_file(mirror_dir, suite_name, component, arch_name):
    contents_basename = "Contents-%s.gz" % (arch_name)
    contents_fname = os.path.join(mirror_dir, "dists", suite_name, component, contents_basename)

    # Ubuntu does not place the Contents file in a component-specific directory,
    # so fall back to the global one.
    if not os.path.isfile(contents_fname):
        path = os.path.join(mirror_dir, "dists", suite_name, contents_basename)
        if os.path.isfile(path):
            contents_fname = path

    # we want information about the whole package, not only the package-name
    packages_dict = dict()
    for name, pkg in read_packages_dict_from_file(mirror_dir, suite_name, component, arch_name, with_description=False).items():
        pkg.filename = os.path.join(mirror_dir, pkg.filename)
        packages_dict[name] = pkg

    # load and preprocess the large Contents file.
    with gzip.open(contents_fname, 'r') as f:
        for line in f:
            line = _decode_contents_line(line)
            fname, pkgname = _file_pkg_from_contents_line(line)
            pkg = packages_dict.get(pkgname)
            if not pkg:
                continue
            yield fname, pkg


__all__.append('parse_contents_file')
