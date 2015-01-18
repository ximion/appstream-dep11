#!/usr/bin/env python
# Copyright (c) 2014 Abhishek Bhattacharjee <abhishek.bhattacharjee11@gmail.com>
# Copyright (c) 2014 Matthias Klumpp <mak@debian.org>
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
import fnmatch
import urllib
from apt_inst import DebFile
import cStringIO as StringIO

import cairo
import rsvg
from tempfile import NamedTemporaryFile
from PIL import Image

from dep11.component import DEP11Component, IconSize
from dep11.find_metainfo import IconFinder
from dep11.parsers import read_desktop_data, read_appstream_upstream_xml

from daklib.config import Config

xdg_icon_sizes = [IconSize(64), IconSize(72), IconSize(96), IconSize(128),
                    IconSize(256), IconSize(256), IconSize(512)]

class MetadataExtractor:
    '''
    Takes a deb file and extracts component metadata from it.
    '''

    def __init__(self, suite_name, component, pkgname, metainfo_files, binid, pkg_fname):
        '''
        Initialize the object with List of files.
        '''
        self._filename = pkg_fname
        self._deb = None
        try:
            self._deb = DebFile(self._filename)
        except Exception as e:
            print ("Error reading deb file '%s': %s" % (self._filename , e))

        self._suite_name = suite_name
        self._component = component
        self._pkgname = pkgname
        self._mfiles = metainfo_files
        self._binid = binid
        self._dep11_cpts = list()

        cnf = Config()
        component_basepath = "%s/%s/%s-%s" % (self._suite_name, self._component,
                                self._pkgname, str(self._binid))
        self._export_path = "%s/%s" % (cnf["Dir::MetaInfo"], component_basepath)
        self._public_url = "%s/%s" % (cnf["DEP11::Url"], component_basepath)

        # list of large sizes to scale down, in order to find more icons
        self._large_icon_sizes = xdg_icon_sizes[:]
        # list of icon sizes we want
        self._icon_sizes = list()
        for strsize in cnf.value_list('DEP11::IconSizes'):
            self._icon_sizes.append(IconSize(strsize))

        # remove smaller icons - we don't want to scale up icons later
        while (len(self._large_icon_sizes) > 0) and (int(self._icon_sizes[0]) >= int(self._large_icon_sizes[0])):
            del self._large_icon_sizes[0]

    @property
    def metadata(self):
        return self._dep11_cpts

    @metadata.setter
    def metadata(self, val):
        self._dep11_cpts = val

    def _deb_filelist(self):
        '''
        Returns a list of all files in a deb package
        '''
        files = list()
        if not self._deb:
            return files
        try:
            self._deb.data.go(lambda item, data: files.append(item.name))
        except SystemError:
            print ("ERROR: List of files for '%s' could not be read" % (self._filename))
            return None

        return files

    def _scale_screenshot(self, imgsrc, cpt_export_path, cpt_scr_url):
        '''
        scale images in three sets of two-dimensions
        (752x423 624x351 and 112x63)
        '''
        thumbnails = []
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

    def _fetch_screenshots(self, cpt):
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
            path = os.path.join(self._export_path, "screenshots")
            base_url = os.path.join(self._public_url, "screenshots")
            imgsrc = os.path.join(path, "source", "screenshot-%s.png" % (str(cnt)))
            try:
                image = urllib.urlopen(origin_url).read()
                if not os.path.exists(os.path.dirname(imgsrc)):
                    os.makedirs(os.path.dirname(imgsrc))
                f = open(imgsrc, 'wb')
                f.write(image)
                f.close()
            except Exception as e:
                cpt.add_hint("Error while downloading screenshot from '%s' for component '%s': %s" % (origin_url, cpt.cid, str(e)))
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
                cpt.add_hint("Error while reading screenshot data for 'screenshot-%s.png' of component '%s': %s" % (str(cnt), cpt.cid, str(e)))
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
        ext_allowed = ('.png', '.svg', '.xcf', '.gif', '.svgz', '.jpg')
        if icon.endswith(ext_allowed):
            return True
        return False

    def _render_svg_to_png(self, data, store_path, width, height):
        '''
        Uses cairosvg to render svg data to png data.
        '''

        img =  cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(img)
        ctx.scale(1,1);
        handler= rsvg.Handle(None, data)
        handler.render_cairo(ctx)

        img.write_to_png(store_path)

    def _store_icon(self, cpt, icon_path, deb_fname, size):
        '''
        Extracts the icon from the deb package and stores it in the cache.
        '''
        svgicon = False
        if not self._icon_allowed(icon_path):
            cpt.add_ignore_reason("Icon file '%s' uses an unsupported image file format." % (os.path.basename(icon_path)))
            return False

        if not os.path.exists(deb_fname):
            return False

        path = "%s/icons/%s/" % (self._export_path, str(size))
        icon_name = "%s_%s" % (self._pkgname, os.path.basename(icon_path))
        if icon_name.endswith(".svg"):
            svgicon = True
            icon_name = icon_name.replace(".svg", ".png")
        cpt.icon = icon_name

        icon_store_location = "{0}/{1}".format(path, icon_name)
        if os.path.exists(icon_store_location):
            # we already extracted that icon, skip this step
            return True

        # filepath is checked because icon can reside in another binary
        # eg amarok's icon is in amarok-data
        try:
            icon_data = DebFile(deb_fname).data.extractdata(icon_path)
        except Exception as e:
            print("Error while extracting icon '%s': %s" % (deb_fname, e))
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
                stream = StringIO.StringIO(icon_data)
                stream.seek(0)
                img = None
                try:
                    img = Image.open(stream)
                except Exception as e:
                    cpt.add_ignore_reason("Unable to open icon file '%s'. Error: %s" % (icon_name, str(e)))
                    return False
                newimg = img.resize((int(size), int(size)), Image.ANTIALIAS)
                newimg.save(icon_store_location)
                return True

        return False

    def _match_and_store_icon(self, cpt, filelist, icon_name, size):
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
                success = self._store_icon(cpt, filtered[0], self._filename, asize) or success
        else:
            success = self._store_icon(cpt, filtered[0], self._filename, size)
        return success

    def _fetch_icon(self, cpt, filelist):
        '''
        Searches for icon if absolute path to an icon
        is not given. Component with invalid icons are ignored
        '''
        if not cpt.icon:
            # keep metadata if Icon self itself is not present
            return True

        icon_str = cpt.icon
        cpt.icon = None

        success = False
        if icon_str.startswith("/"):
            if icon_str[1:] in filelist:
                return self._store_icon(cpt, icon_str[1:], self._filename, IconSize(64))
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
                success = self._match_and_store_icon(cpt, filelist, icon_name_ext, size) or success
            if not success:
                # we cheat and test for larger icons as well, which can be scaled down
                # first check for a scalable graphic
                # TODO: Deal with SVGZ icons
                success = self._match_and_store_icon(cpt, filelist, icon_str + ".svg", "scalable")
                # then try to scale down larger graphics
                if not success:
                    for size in self._large_icon_sizes:
                        success = self._match_and_store_icon(cpt, filelist, icon_name_ext, size) or success

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
                            return self._store_icon(cpt, path, self._filename, IconSize(64))
                        last_pixmap = path
            if last_pixmap:
                # we don't do a global icon search anymore, since we've found an (unsuitable) icon
                # already
                cpt.add_ignore_reason("Icon file '%s' uses an unsupported image file format." % (os.path.basename(last_pixmap)))
                return False

            # the IconFinder uses it's own, new session, since we run multiprocess here
            ficon = IconFinder(self._pkgname, icon_str, self._binid, self._suite_name, self._component)
            all_icon_sizes = self._icon_sizes
            all_icon_sizes.extend(self._large_icon_sizes)
            icon_dict = ficon.get_icons(all_icon_sizes)
            ficon.close()
            success = False
            if icon_dict:
                for size in self._icon_sizes:
                    if not size in icon_dict:
                        continue
                    filepath = (Config()["Dir::Pool"] +
                                cpt._component + '/' + icon_dict[size][1])
                    success = self._store_icon(cpt, icon_dict[size][0], filepath, size) or success
                if not success:
                    for size in self._large_icon_sizes:
                        if not size in icon_dict:
                            continue
                        filepath = (Config()["Dir::Pool"] +
                                    cpt._component + '/' + icon_dict[size][1])
                        for asize in self._icon_sizes:
                            success = self._store_icon(cpt, icon_dict[size][0], filepath, asize) or success
                return success

            cpt.add_ignore_reason("Icon '%s' was not found in the archive or is not available in a suitable size (at least 64x64)." % (icon_str))
            return False

        return True

    def process(self):
        '''
        Reads the metadata from the xml file and the desktop files.
        And returns a list of DEP11Component objects.
        '''
        if not self._deb:
            return list()
        suitename = self._suite_name
        filelist = self._deb_filelist()
        component_dict = dict()

        if not filelist:
            compdata = DEP11Component(suitename, self._component, self._binid, self._pkgname)
            compdata.add_ignore_reason("Could not determine file list for '%s'" % (os.path.basename(self._filename)))
            return [compdata]

        component_dict = dict()

        # first cache all additional metadata (.desktop/.pc/etc.) files
        mdata_raw = dict()
        for meta_file in self._mfiles:
            if meta_file.endswith(".desktop"):
                # We have a .desktop file
                dcontent = None
                cpt_id = os.path.basename(meta_file)

                error = None
                try:
                    dcontent = str(self._deb.data.extractdata(meta_file))
                except Exception as e:
                    error = "Could not extract file '%s' from package '%s'. Error: %s" % (cpt_id, os.path.basename(self._filename), str(e))
                if not dcontent and not error:
                    error = "File '%s' from package '%s' appeared empty." % (cpt_id, os.path.basename(self._filename))
                mdata_raw[cpt_id] = {'error': error, 'data': dcontent}

        # process all AppStream XML files
        for meta_file in self._mfiles:
            if meta_file.endswith(".xml"):
                xml_content = None
                compdata = DEP11Component(suitename, self._component, self._binid, self._pkgname)

                try:
                    xml_content = str(self._deb.data.extractdata(meta_file))
                except Exception as e:
                    # inability to read an AppStream XML file is a valid reason to skip the whole package
                    compdata.add_ignore_reason("Could not extract file '%s' from package '%s'. Error: %s" % (meta_file, self._filename, str(e)))
                    return [compdata]
                if not xml_content:
                    continue

                read_appstream_upstream_xml(compdata, xml_content)
                # Reads the desktop files associated with the xml file
                if not compdata.cid:
                    # if there is no ID at all, we dump this component, since we cannot do anything with it at all
                    compdata.add_ignore_reason("Could not determine an id for this component.")
                    continue

                component_dict[compdata.cid] = compdata
                if compdata.kind == "desktop-app":
                    data = mdata_raw.get(compdata.cid)
                    if not data:
                        compdata.add_ignore_reason("Found an AppStream upstream XML file, but the associated .desktop file is missing.")
                        continue
                    if data['error']:
                        # add a non-fatal hint that we couldn't process the .desktop file
                        compdata.add_hint(data['error'])
                    else:
                        # we have a .desktop component, extend it with the associated .desktop data
                        read_desktop_data(compdata, data['data'])
                    del mdata_raw[compdata.cid]

        # now process the remaining metadata files, which have not been processed together with the XML
        for mid, mdata in mdata_raw.items():
            if mid.endswith(".desktop"):
                # We have a .desktop file
                compdata = DEP11Component(suitename, self._component, self._binid, self._pkgname)
                compdata.cid = mid

                if mdata['error']:
                    # add a fatal hint that we couldn't process this file
                    compdata.add_ignore_reason(mdata['error'])
                else:
                    ret = read_desktop_data(compdata, mdata['data'])
                    if ret or not compdata.has_ignore_reason():
                        component_dict[compdata.cid] = compdata
                    else:
                        # this means that reading the .desktop file failed and we should
                        # silently ignore this issue (since the file was marked to be invisible on purpose)
                        pass

        for cpt in component_dict.values():
            self._fetch_icon(cpt, filelist)
            if cpt.kind == 'desktop-app' and not cpt.icon:
                cpt.add_ignore_reason("GUI application, but no valid icon found.")
            else:
                self._fetch_screenshots(cpt)

        self._dep11_cpts = component_dict.values()
