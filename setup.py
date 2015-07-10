#!/usr/bin/env python3
#
# Copyright (C) 2014-2015 Matthias Klumpp <matthias@tenstral.net>
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

from setuptools import setup

setup(name = 'dep11',
      version = '0.1',
      description = 'DEP-11 metadata tools for Debian',
      url = 'https://github.com/ximion/dep11', # TODO: Move that to Debian infrastructure soon
      author = 'Matthias Klumpp',
      author_email = 'mak@debian.org',
      license = 'LGPL-2.1+',
      packages = ['dep11'],
      scripts = ['scripts/dep11-generator', 'scripts/dep11-validate'],
      zip_safe = False,
     )
