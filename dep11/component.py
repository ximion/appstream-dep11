#!/usr/bin/env python

"""
Contains the definition of a DEP-11 component.
"""

# Copyright (c) 2014 Abhishek Bhattacharjee <abhishek.bhattacharjee11@gmail.com>
# Copyright (c) 2014 Matthias Klumpp <mak@debian.org>
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

import yaml
import datetime
from dep11.utils import str_enc_dec

###########################################################################
DEP11_VERSION = "0.6"
time_str = str(datetime.date.today())
dep11_header_template = {
    "File": "DEP-11",
    "Version": DEP11_VERSION
}
###########################################################################

class DEP11YamlDumper(yaml.Dumper):
    '''
    Custom YAML dumper, to ensure resulting YAML file can be read by
    all parsers (even the Java one)
    '''
    def increase_indent(self, flow=False, indentless=False):
        return super(DEP11YamlDumper, self).increase_indent(flow, False)

def get_dep11_header(suite_name, component_name):
    head_dict = dep11_header_template
    head_dict['Origin'] = "%s-%s" % (suite_name, component_name)
    return yaml.dump(head_dict, Dumper=DEP11YamlDumper,
                            default_flow_style=False, explicit_start=True,
                            explicit_end=False, width=200, indent=2)

class IconSize:
    '''
    A simple type representing an icon size
    '''
    size = int()

    def __init__(self, size):
        if isinstance(size, str):
            self.set_from_string(size)
        else:
            self.size = size

    def __str__(self):
        return "%ix%i" % (self.size, self.size)

    def __int__(self):
        return self.size

    def set_from_string(self, s):
        wd, ht = s.split('x')
        if int(wd) != int(ht):
            print("Warning: Processing asymetric icon.")
        self.size = int(wd)

class ProvidedItemType:
    '''
    Types supported as publicly provided interfaces. Used as keys in
    the 'Provides' field
    '''
    BINARY = 'binaries'
    LIBRARY = 'libraries'
    MIMETYPE = 'mimetypes'
    DBUS = 'dbus'
    PYTHON_2 = 'python2'
    PYTHON_3 = 'python3'
    FIRMWARE = 'firmware'
    CODEC = 'codecs'

class HintImportance:
    '''
    Importance of a component parsing hint.
    '''
    ERROR = 'errors'
    WARNING = 'warnings'
    INFO = 'infos'

class DEP11Component:
    '''
    Used to store the properties of component data. Used by MetadataExtractor
    '''

    def __init__(self, suitename, component, binid, pkg):
        '''
        Used to set the properties to None.
        '''
        self._suitename = suitename
        self._component = component
        self._pkg = pkg
        self._binid = binid

        # properties
        self._hints = dict()
        self._ignore = False

        self._id = None
        self._type = None
        self._name = dict()
        self._categories = None
        self._icon = None
        self._summary = dict()
        self._description = None
        self._screenshots = None
        self._keywords = None
        self._archs = None
        self._provides = dict()
        self._url = None
        self._project_license = None
        self._project_group = None
        self._developer_name = dict()
        self._extends = list()
        self._compulsory_for_desktops = list()

    def add_hint(self, msg, importance):
        if not self._hints.get(importance):
            self._hints[importance] = list()
        self._hints[importance].append(msg)

    def add_error_hint(self, msg):
        self.add_hint(msg, HintImportance.ERROR)
        self._ignore = True

    def add_warning_hint(self, msg):
        self.add_hint(msg, HintImportance.WARNING)

    def add_info_hint(self, msg):
        self.add_hint(msg, HintImportance.INFO)

    def has_ignore_reason(self):
        return self._ignore

    def get_hints_dict(self):
        if not self._hints:
            return None
        hdict = dict()
        # add some helpful data
        if self.cid:
            hdict['ID'] = self.cid
        if self.kind:
            hdict['Type'] = self.kind
        if self._pkg:
            hdict['Package'] = self._pkg
        if self.has_ignore_reason():
            hdict['Ignored'] = True
        hdict['Hints'] = self._hints

        return hdict

    def get_hints_yaml(self):
        if not self._hints:
            return None
        return yaml.dump(self.get_hints_dict(), Dumper=DEP11YamlDumper,
                    default_flow_style=False, explicit_start=True,
                    explicit_end=False, width=100, indent=2,
                    allow_unicode=True)

    @property
    def cid(self):
        return self._id

    @cid.setter
    def cid(self, val):
        self._id = val

    @property
    def kind(self):
        return self._type

    @kind.setter
    def kind(self, val):
        self._type = val

    @property
    def pkgname(self):
        return self._pkg

    @property
    def binid(self):
        return self._binid

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, val):
        self._name = val

    @property
    def categories(self):
        return self._categories

    @categories.setter
    def categories(self, val):
        self._categories = val

    @property
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, val):
        self._icon = val

    @property
    def summary(self):
        return self._summary

    @summary.setter
    def summary(self, val):
        self._summary = val

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, val):
        self._description = val

    @property
    def screenshots(self):
        return self._screenshots

    @screenshots.setter
    def screenshots(self, val):
        self._screenshots = val

    @property
    def keywords(self):
        return self._keywords

    @keywords.setter
    def keywords(self, val):
        self._keywords = val

    @property
    def archs(self):
        return self._archs

    @archs.setter
    def archs(self, val):
        self._archs = val

    @property
    def provides(self):
        return self._provides

    @provides.setter
    def provides(self, val):
        self._provides = val

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, val):
        self._url = val

    @property
    def compulsory_for_desktops(self):
        return self._compulsory_for_desktops

    @compulsory_for_desktops.setter
    def compulsory_for_desktops(self, val):
        self._compulsory_for_desktops = val

    @property
    def project_license(self):
        return self._project_license

    @project_license.setter
    def project_license(self, val):
        self._project_license = val

    @property
    def project_group(self):
        return self._project_group

    @project_group.setter
    def project_group(self, val):
        self._project_group = val

    @property
    def developer_name(self):
        return self._developer_name

    @developer_name.setter
    def developer_name(self, val):
        self._developer_name = val

    @property
    def extends(self):
        return self._extends

    @extends.setter
    def extends(self, val):
        self._extends = val

    def add_provided_item(self, kind, value):
        if kind not in self.provides.keys():
            self.provides[kind] = list()
        self.provides[kind].append(value)


    def _is_quoted(self, s):
        return (s.startswith("\"") and s.endswith("\"")) or (s.startswith("\'") and s.endswith("\'"))

    def _cleanup(self, d):
        '''
        Remove cruft locale, duplicates and extra encoding information
        '''
        if not d:
            return d

        if d.get('x-test'):
            d.pop('x-test')
        if d.get('xx'):
            d.pop('xx')

        unlocalized = d.get('C')
        if unlocalized:
            to_remove = []
            for k in list(d.keys()):
                val = d[k]
                # don't duplicate strings
                if val == unlocalized and k != 'C':
                    d.pop(k)
                    continue
                if self._is_quoted(val):
                    d[k] = val.strip("\"'")
                # should not specify encoding
                if k.endswith('.UTF-8'):
                    locale = k.strip('.UTF-8')
                    d.pop(k)
                    d[locale] = val
                    continue

        return d

    def finalize_to_dict(self):
        '''
        Do sanity checks and finalization work, then serialize the component to
        a Python dict.
        '''

        # perform some cleanup work
        self.name = self._cleanup(self.name)
        self.summary = self._cleanup(self.summary)
        self.description = self._cleanup(self.description)
        self.developer_name = self._cleanup(self.developer_name)
        if self.screenshots:
            for shot in self.screenshots:
                caption = shot.get('caption')
                if caption:
                    shot['caption'] = self._cleanup(caption)

        # validate the basics (if we don't ignore this already)
        if not self.has_ignore_reason():
            if not self.cid:
                self.add_error_hint("Component has no valid ID.")
            if not self.kind:
                self.add_error_hint("Component has no type defined.")
            if not self.name:
                self.add_error_hint("Component has no name specified.")
            if not self._pkg:
                self.add_error_hint("Component has no package defined.")
            if not self.summary:
                self.add_error_hint("Component does not contain a short summary.")

        d = dict()
        d['Packages'] = [self._pkg]
        if self.cid:
            d['ID'] = self.cid
        if self.kind:
            d['Type'] = self.kind

        # check if we need to print ignore information, instead
        # of exporting the software component
        if self.has_ignore_reason():
            d['Ignored'] = True
            return d

        if self.name:
            d['Name'] = self.name
        if self.summary:
            d['Summary'] = self.summary
        if self.categories:
            d['Categories'] = self.categories
        if self.description:
            d['Description'] = self.description
        if self.keywords:
            d['Keywords'] = self.keywords
        if self.screenshots:
            d['Screenshots'] = self.screenshots
        if self.archs:
            d['Architectures'] = self.archs
        if self.icon:
            d['Icon'] = {'cached': self.icon}
        if self.url:
            d['Url'] = self.url
        if self.provides:
            d['Provides'] = self.provides
        if self.project_license:
            d['ProjectLicense'] = self.project_license
        if self.project_group:
            d['ProjectGroup'] = self.project_group
        if self.developer_name:
            d['DeveloperName'] = self.developer_name
        if self.extends:
            d['Extends'] = self.extends
        if self.compulsory_for_desktops:
            d['CompulsoryForDesktops'] = self.compulsory_for_desktops
        return d

    def to_yaml_doc(self):
        return yaml.dump(self.finalize_to_dict(), Dumper=DEP11YamlDumper,
                    default_flow_style=False, explicit_start=True,
                    explicit_end=False, width=100, indent=2,
                    allow_unicode=True)
