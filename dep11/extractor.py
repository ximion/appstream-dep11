#!/usr/bin/env python3
#
# Copyright (c) 2014 Abhishek Bhattacharjee <abhishek.bhattacharjee11@gmail.com>
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
import fnmatch
import urllib.request
import ssl
from apt_inst import DebFile
from io import BytesIO

import zlib
import cairo
from gi.repository import Rsvg
from tempfile import NamedTemporaryFile
from PIL import Image
import logging as log

from dep11.component import DEP11Component, IconSize
from dep11.parsers import read_desktop_data, read_appstream_upstream_xml
from dep11.iconfinder import AbstractIconFinder

xdg_icon_sizes = [IconSize(64), IconSize(72), IconSize(96), IconSize(128),
                    IconSize(256), IconSize(512)]

class MetadataExtractor:
    '''
    Takes a deb file and extracts component metadata from it.
    '''

    def __init__(self, suite_name, component, export_dir, base_url, icon_sizes, icon_finder=None):
        '''
        Initialize the object with List of files.
        '''
        self._suite_name = suite_name
        self._archive_component = component
        self._export_dir = export_dir
        self._base_url = base_url

        self._icon_ext_allowed = ('.png', '.svg', '.xcf', '.gif', '.svgz', '.jpg')

        if icon_finder:
            self._icon_finder = icon_finder
            self._icon_finder.set_allowed_icon_extensions(self._icon_ext_allowed)
        else:
            self._icon_finder = AbstractIconFinder(self._suite_name, self._archive_component)

        # list of large sizes to scale down, in order to find more icons
        self._large_icon_sizes = xdg_icon_sizes[:]
        # list of icon sizes we want
        self._icon_sizes = list()
        for strsize in icon_sizes:
            self._icon_sizes.append(IconSize(strsize))

        # remove smaller icons - we don't want to scale up icons later
        while (len(self._large_icon_sizes) > 0) and (int(self._icon_sizes[0]) >= int(self._large_icon_sizes[0])):
            del self._large_icon_sizes[0]

    @property
    def icon_finder(self):
        return self._icon_finder

    @icon_finder.setter
    def icon_finder(self, val):
        self._icon_finder = val

    def _get_deb_filelist(self, deb):
        '''
        Returns a list of all files in a deb package
        '''
        files = list()
        if not deb:
            return files
        try:
            deb.data.go(lambda item, data: files.append(item.name))
        except SystemError as e:
            raise e

        return files

    def _scale_screenshot(self, imgsrc, cpt_export_path, cpt_scr_url):
        '''
        scale images in three sets of two-dimensions
        (752x423 624x351 and 112x63)
        '''
        thumbnails = list()
        name = os.path.basename(imgsrc)
        sizes = ['752x423', '624x351', '112x63']
        for size in sizes:
            wd, ht = size.split('x')
            img = Image.open(imgsrc)
            newimg = img.resize((int(wd), int(ht)), Image.ANTIALIAS)
            newpath = os.path.join(cpt_export_path, size)
            if not os.path.exists(newpath):
                os.makedirs(newpath)
            newimg.save(os.path.join(newpath, name))
            url = "%s/%s/%s" % (cpt_scr_url, size, name)
            thumbnails.append({'url': url, 'height': int(ht),
                               'width': int(wd)})

        return thumbnails

    def _fetch_screenshots(self, cpt, cpt_export_path, cpt_public_url):
        '''
        Fetches screenshots from the given url and
        stores it in png format.
        '''

        if not cpt.screenshots:
            # don't ignore metadata if screenshots itself is not present
            return True

        success = True
        shots = list()
        cnt = 1
        for shot in cpt.screenshots:
            # cache some locations which we need later
            origin_url = shot['source-image']['url']
            if not origin_url:
                # url empty? skip this screenshot
                continue
            path = os.path.join(cpt_export_path, "screenshots")
            base_url = os.path.join(cpt_public_url, "screenshots")
            imgsrc = os.path.join(path, "source", "screenshot-%s.png" % (str(cnt)))

            # The Debian services use a custom setup for SSL verification, not trusting global CAs and
            # only Debian itself. If we are running on such a setup, ensure we load the global CA certs
            # in order to establish HTTPS connections to foreign services.
            # For more information, see https://wiki.debian.org/ServicesSSL
            context = None
            ca_path = '/etc/ssl/ca-global'
            if os.path.isdir(ca_path):
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, capath=ca_path)
            else:
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

            try:
                # FIXME: The context parameter is only supported since Python 3.4.3, which is not
                # yet widely available, so we can't use it here...
                #! image = urllib.request.urlopen(origin_url, context=ssl_context).read()
                image_req = urllib.request.urlopen(origin_url)
                if image_req.getcode() != 200:
                    msg = "HTTP status code was %i." % (image_req.getcode())
                    cpt.add_hint("screenshot-download-error", {'url': origin_url, 'cpt_id': cpt.cid, 'error': msg})
                    success = False
                    continue

                if not os.path.exists(os.path.dirname(imgsrc)):
                    os.makedirs(os.path.dirname(imgsrc))
                f = open(imgsrc, 'wb')
                f.write(image_req.read())
                f.close()
            except Exception as e:
                cpt.add_hint("screenshot-download-error", {'url': origin_url, 'cpt_id': cpt.cid, 'error': str(e)})
                success = False
                continue

            try:
                img = Image.open(imgsrc)
                wd, ht = img.size
                shot['source-image']['width'] = wd
                shot['source-image']['height'] = ht
                shot['source-image']['url'] = os.path.join(base_url, "source", "screenshot-%s.png" % (str(cnt)))
                img.close()
            except Exception as e:
                sname = "screenshot-%is.png" % (cnt)
                cpt.add_hint("screenshot-read-error", {'screenshot_name': sname, 'cpt_id': cpt.cid, 'error': str(e)})
                success = False
                continue

            # scale_screenshots will return a list of
            # dicts with {height,width,url}
            shot['thumbnails'] = self._scale_screenshot(imgsrc, path, base_url)
            shots.append(shot)
            cnt = cnt + 1

        cpt.screenshots = shots
        return success

    def _icon_allowed(self, icon):
        if icon.endswith(self._icon_ext_allowed):
            return True
        return False

    def _render_svg_to_png(self, data, store_path, width, height):
        '''
        Uses cairosvg to render svg data to png data.
        '''

        img =  cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(img)

        handle = Rsvg.Handle()
        svg = handle.new_from_data(data)

        wscale = float(width)/float(svg.props.width)
        hscale = float(height)/float(svg.props.height)
        ctx.scale(wscale, hscale);

        svg.render_cairo(ctx)

        img.write_to_png(store_path)

    def _store_icon(self, cpt, cpt_export_path, icon_path, deb_fname, size):
        '''
        Extracts the icon from the deb package and stores it in the cache.
        '''
        svgicon = False
        if not self._icon_allowed(icon_path):
            cpt.add_hint("icon-format-unsupported", {'icon_fname': os.path.basename(icon_path)})
            return False

        if not os.path.exists(deb_fname):
            return False

        path = "%s/icons/%s/" % (cpt_export_path, str(size))
        icon_name = "%s_%s" % (cpt.pkgname, os.path.basename(icon_path))
        icon_name_orig = icon_name

        icon_name = icon_name.replace(".svgz", ".png")
        icon_name = icon_name.replace(".svg", ".png")
        icon_store_location = "{0}/{1}".format(path, icon_name)

        if os.path.exists(icon_store_location):
            # we already extracted that icon, skip the extraction step
            # change scalable vector graphics to their .png extension
            cpt.icon = icon_name
            return True

        # filepath is checked because icon can reside in another binary
        # eg amarok's icon is in amarok-data
        try:
            icon_data = DebFile(deb_fname).data.extractdata(icon_path)
        except Exception as e:
            cpt.add_hint("deb-extract-error", {'fname': icon_name, 'pkg_fname': deb_fname, 'error': str(e)})
            return False

        cpt.icon = icon_name

        if icon_name_orig.endswith(".svg"):
            svgicon = True
        elif icon_name_orig.endswith(".svgz"):
            svgicon = True
            try:
                icon_data = zlib.decompress(bytes(icon_data), 15+32)
            except Exception as e:
                cpt.add_hint("svgz-decompress-error", {'icon_name': icon_name, 'error': str(e)})
                return False

        if icon_data:
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path))

            if svgicon:
                # render the SVG to a bitmap
                self._render_svg_to_png(icon_data, icon_store_location, int(size), int(size))
                return True
            else:
                # we don't trust upstream to have the right icon size present, and therefore
                # always adjust the icon to the right size
                stream = BytesIO(icon_data)
                stream.seek(0)
                img = None
                try:
                    img = Image.open(stream)
                except Exception as e:
                    cpt.add_hint("Unable to open icon file '%s'. Error: %s" % (icon_name, str(e)))
                    return False
                newimg = img.resize((int(size), int(size)), Image.ANTIALIAS)
                newimg.save(icon_store_location)
                return True

        return False

    def _match_and_store_icon(self, cpt, cpt_export_path, pkg_fname, filelist, icon_name, size):
        success = False
        if size == "scalable":
            size_str = "scalable"
        else:
            size_str = str(size)
        icon_path = "usr/share/icons/hicolor/%s/*/%s" % (size_str, icon_name)
        filtered = fnmatch.filter(filelist, icon_path)
        if not filtered:
            return False
        if not size in self._icon_sizes:
            for asize in self._icon_sizes:
                success = self._store_icon(cpt, cpt_export_path, filtered[0], pkg_fname, asize) or success
        else:
            success = self._store_icon(cpt, cpt_export_path, filtered[0], pkg_fname, size)
        return success

    def _fetch_icon(self, cpt, cpt_export_path, pkg_fname, filelist):
        '''
        Searches for icon if absolute path to an icon
        is not given. Component with invalid icons are ignored
        '''
        if not cpt.icon:
            # if we don't know an icon-name or path, just return without error
            return True

        icon_str = cpt.icon
        cpt.icon = None

        success = False
        if icon_str.startswith("/"):
            if icon_str[1:] in filelist:
                return self._store_icon(cpt, cpt_export_path, icon_str[1:], pkg_fname, IconSize(64))
        else:
            ret = False
            icon_str = os.path.basename (icon_str)
            # check if there is some kind of file-extension.
            # if there is none, the referenced icon is likely a stock icon, and we assume .png
            if "." in icon_str:
                icon_name_ext = icon_str
            else:
                icon_name_ext = icon_str + ".png"
            for size in self._icon_sizes:
                success = self._match_and_store_icon(cpt, cpt_export_path, pkg_fname, filelist, icon_name_ext, size) or success
            if not success:
                # we cheat and test for larger icons as well, which can be scaled down
                # first check for a scalable graphic
                success = self._match_and_store_icon(cpt, cpt_export_path, pkg_fname, filelist, icon_str + ".svg", "scalable")
                if not success:
                    success = self._match_and_store_icon(cpt, cpt_export_path, pkg_fname, filelist, icon_str + ".svgz", "scalable")
                # then try to scale down larger graphics
                if not success:
                    for size in self._large_icon_sizes:
                        success = self._match_and_store_icon(cpt, cpt_export_path, pkg_fname, filelist, icon_name_ext, size) or success

        if not success:
            last_pixmap = None
            # handle stuff in the pixmaps directory
            for path in filelist:
                if path.startswith("usr/share/pixmaps"):
                    file_basename = os.path.basename(path)
                    if ((file_basename == icon_str) or (os.path.splitext(file_basename)[0] == icon_str)):
                        # the pixmap dir can contain icons in multiple formats, and store_icon() fails in case
                        # the icon format is not allowed. We therefore only exit here, if the icon has a valid format
                        if self._icon_allowed(path):
                            return self._store_icon(cpt, cpt_export_path, path, pkg_fname, IconSize(64))
                        last_pixmap = path
            if last_pixmap:
                # we don't do a global icon search anymore, since we've found an (unsuitable) icon
                # already
                cpt.add_hint("icon-format-unsupported", {'icon_fname': os.path.basename(last_pixmap)})
                return False

            # the IconFinder uses it's own, new session, since we run multiprocess here
            all_icon_sizes = self._icon_sizes[:]
            all_icon_sizes.extend(self._large_icon_sizes)
            icon_dict = self._icon_finder.find_icons(cpt.pkgname, icon_str, all_icon_sizes, cpt.binid)
            success = False
            if icon_dict:
                for size in self._icon_sizes:
                    if not size in icon_dict:
                        continue

                    success = self._store_icon(cpt,
                                        cpt_export_path,
                                        icon_dict[size]['icon_fname'],
                                        icon_dict[size]['deb_fname'],
                                        size) or success
                if not success:
                    for size in self._large_icon_sizes:
                        if not size in icon_dict:
                            continue
                        for asize in self._icon_sizes:
                            success = self._store_icon(cpt,
                                        cpt_export_path,
                                        icon_dict[size]['icon_fname'],
                                        icon_dict[size]['deb_fname'],
                                        asize) or success
                return success

            if ("." in icon_str) and (not self._icon_allowed(icon_str)):
                cpt.add_hint("icon-format-unsupported", {'icon_fname': icon_str})
            else:
                cpt.add_hint("icon-not-found", {'icon_fname': icon_str})
            return False

        return True

    def process(self, pkgname, pkg_fname, metainfo_files=None, binid=-1):
        '''
        Reads the metadata from the xml file and the desktop files.
        And returns a list of DEP11Component objects.
        '''
        deb = None
        try:
            deb = DebFile(pkg_fname)
        except Exception as e:
            log.error("Error reading deb file '%s': %s" % (pkg_fname, e))
        if not deb:
            return list()

        try:
            filelist = self._get_deb_filelist(deb)
        except:
            log.error("List of files for '%s' could not be read" % (pkg_fname))
            filelist = None

        if not filelist:
            cpt = DEP11Component(self._suite_name, self._archive_component, binid, pkgname)
            cpt.add_hint("deb-filelist-error", {'pkg_fname': os.path.basename(pkg_fname)})
            return [cpt]

        if binid > 0:
            component_basepath = "%s/%s" % (self._archive_component,
                                    pkgname, str(binid))
        else:
            idname, ext = os.path.splitext(os.path.basename(pkg_fname))
            if not idname:
                idname = os.path.basename(pkg_fname)
            component_basepath = "%s/%s" % (self._archive_component, idname)
        export_path = "%s/%s" % (self._export_dir, component_basepath)
        public_url = "%s/%s" % (self._base_url, component_basepath)

        component_dict = dict()

        # if we don't have an explicit list of interesting files, we simply scan all
        if not metainfo_files:
            metainfo_files = filelist

        # first cache all additional metadata (.desktop/.pc/etc.) files
        mdata_raw = dict()
        for meta_file in metainfo_files:
            if meta_file.endswith(".desktop") and meta_file.startswith("usr/share/applications"):
                # We have a .desktop file
                dcontent = None
                cpt_id = os.path.basename(meta_file)

                error = None
                try:
                    dcontent = str(deb.data.extractdata(meta_file).decode("utf-8"))
                except Exception as e:
                    error = {'tag': "deb-extract-error",
                                'params': {'fname': cpt_id, 'pkg_fname': os.path.basename(pkg_fname), 'error': str(e)}}
                if not dcontent and not error:
                    error = {'tag': "deb-empty-file",
                                'params': {'fname': cpt_id, 'pkg_fname': os.path.basename(pkg_fname)}}
                mdata_raw[cpt_id] = {'error': error, 'data': dcontent}

        # process all AppStream XML files
        for meta_file in metainfo_files:
            if meta_file.endswith(".xml") and meta_file.startswith("usr/share/appdata"):
                xml_content = None
                cpt = DEP11Component(self._suite_name, self._archive_component, binid, pkgname)

                try:
                    xml_content = str(deb.data.extractdata(meta_file).decode("utf-8"))
                except Exception as e:
                    # inability to read an AppStream XML file is a valid reason to skip the whole package
                    cpt.add_hint("deb-extract-error", {'fname': meta_file, 'pkg_fname': os.path.basename(pkg_fname), 'error': str(e)})
                    return [cpt]
                if not xml_content:
                    continue

                read_appstream_upstream_xml(cpt, xml_content)
                # Reads the desktop files associated with the xml file
                if not cpt.cid:
                    # if there is no ID at all, we dump this component, since we cannot do anything with it at all
                    cpt.add_hint("metainfo-no-id")
                    continue

                component_dict[cpt.cid] = cpt
                if cpt.kind == "desktop-app":
                    data = mdata_raw.get(cpt.cid)
                    if not data:
                        cpt.add_hint("missing-desktop-file")
                        continue
                    if data['error']:
                        # add a non-fatal hint that we couldn't process the .desktop file
                        cpt.add_hint(data['error']['tag'], data['error']['params'])
                    else:
                        # we have a .desktop component, extend it with the associated .desktop data
                        read_desktop_data(cpt, data['data'])
                    del mdata_raw[cpt.cid]

        # now process the remaining metadata files, which have not been processed together with the XML
        for mid, mdata in mdata_raw.items():
            if mid.endswith(".desktop"):
                # We have a .desktop file
                cpt = DEP11Component(self._suite_name, self._archive_component, binid, pkgname)
                cpt.cid = mid

                if mdata['error']:
                    # add a fatal hint that we couldn't process this file
                    cpt.add_hint(mdata['error']['tag'], mdata['error']['params'])
                    component_dict[cpt.cid] = cpt
                else:
                    ret = read_desktop_data(cpt, mdata['data'])
                    if ret or not cpt.has_ignore_reason():
                        component_dict[cpt.cid] = cpt
                    else:
                        # this means that reading the .desktop file failed and we should
                        # silently ignore this issue (since the file was marked to be invisible on purpose)
                        pass

        for cpt in component_dict.values():
            self._fetch_icon(cpt, export_path, pkg_fname, filelist)
            if cpt.kind == 'desktop-app' and not cpt.icon:
                cpt.add_hint("gui-app-without-icon")
            else:
                self._fetch_screenshots(cpt, export_path, public_url)

        return component_dict.values()
