#!/usr/bin/env python3
#
# Copyright (C) 2015 Matthias Klumpp <mak@debian.org>
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
import sys
import yaml
import apt_pkg
import gzip
import glob
import shutil
import time
from jinja2 import Environment, FileSystemLoader
import logging as log

from dep11 import DataCache, build_cpt_global_id, build_pkg_id, __version__
from .component import dict_to_dep11_yaml
from .utils import get_data_dir, load_generator_config
from .package import Package, read_packages_dict_from_file
from .hints import get_hint_tag_info
from .validate import DEP11Validator
from .statsgenerator import StatsGenerator

try:
    import pygments
    from pygments.lexers import YamlLexer
    from pygments.formatters import HtmlFormatter
except:
    pygments = None


def equal_dicts(d1, d2, ignore_keys):
    ignored = set(ignore_keys)
    for k1, v1 in d1.items():
        if k1 not in ignored and (k1 not in d2 or d2[k1] != v1):
            return False
    for k2, v2 in d2.items():
        if k2 not in ignored and k2 not in d1:
            return False
    return True


class ReportGenerator:
    def __init__(self):
        pass


    def initialize(self, dep11_dir):
        dep11_dir = os.path.abspath(dep11_dir)

        conf = load_generator_config(dep11_dir)
        if not conf:
            return False

        self._archive_root = conf.get("ArchiveRoot")

        self._html_url = conf.get("HtmlBaseUrl")
        if not self._html_url:
            self._html_url = "."

        self._template_dir = os.path.join(get_data_dir(), "templates", "default")

        self._distro_name = conf.get("DistroName", "Debian")

        self._export_dir = os.path.join(dep11_dir, "export")
        if conf.get("ExportDir"):
            self._export_dir = conf.get("ExportDir")

        if not os.path.exists(self._export_dir):
            os.makedirs(self._export_dir)

        self._suites_data = conf['Suites']

        self._html_export_dir = os.path.join(self._export_dir, "html")

        self._dep11_url = conf.get("MediaBaseUrl")

        # load metadata cache
        cache_dir = os.path.join(dep11_dir, "cache")
        if conf.get("CacheDir"):
            cache_dir = conf.get("CacheDir")
        self._cache = DataCache(os.path.join(self._export_dir, "media"))
        ret = self._cache.open(cache_dir)

        os.chdir(dep11_dir)
        return True


    def _get_packages_for(self, suite, component, arch):
        return read_packages_dict_from_file(self._archive_root, suite, component, arch).values()


    def render_template(self, name, out_dir, out_name = None, *args, **kwargs):
        if not out_name:
            out_path = os.path.join(out_dir, name)
        else:
            out_path = os.path.join(out_dir, out_name)
        # create subdirectories if necessary
        out_dir = os.path.dirname(os.path.realpath(out_path))
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        j2_env = Environment(loader=FileSystemLoader(self._template_dir))

        template = j2_env.get_template(name)
        content = template.render(root_url = self._html_url,
                                    distro = self._distro_name,
                                    time = time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                                    generator_version = __version__,
                                    *args, **kwargs)
        log.debug("Render: %s" % (out_path.replace(self._html_export_dir, "")))
        with open(out_path, 'wb') as f:
            f.write(bytes(content, 'utf-8'))


    def _highlight_yaml(self, yml_data):
        if not yml_data:
            return ""
        if not pygments:
            return yml_data.replace("\n", "<br/>\n")
        return pygments.highlight(yml_data, YamlLexer(), HtmlFormatter())


    def _expand_hint(self, hint_data):
        tag_name = hint_data['tag']
        tag = get_hint_tag_info(tag_name)

        desc = ""
        try:
            desc = tag['text'] % hint_data['params']
        except Exception as e:
            desc = "Error while expanding hint description: %s" % (str(e))

        severity = tag.get('severity')
        if not severity:
            log.error("Tag %s has no severity!", tag_name)
            severity = "info"

        return {'tag_name': tag_name, 'description': desc, 'severity': severity}


    def update_reports(self, suite_name):
        dep11_hintsdir = os.path.join(self._export_dir, "hints")
        if not os.path.exists(dep11_hintsdir):
            return
        dep11_minfodir = os.path.join(self._export_dir, "data")
        if not os.path.exists(dep11_minfodir):
            return

        suite = self._suites_data.get(suite_name)
        if not suite:
            log.error("Suite '%s' not found!" % (suite_name))
            return False

        export_dir_root = self._html_export_dir
        media_dir = os.path.join(self._export_dir, "media")
        noimage_url = os.path.join(self._html_url, "static", "img", "no-image.png")

        # Render archive suites index page
        self.render_template("suites_index.html", export_dir_root, "index.html", suites=self._suites_data.keys())
        export_dir = os.path.join(export_dir_root, suite_name)

        log.info("Collecting metadata and issue information for suite '%s'" % (suite_name))

        stats = StatsGenerator(self._cache)
        suite_error_count = 0
        suite_warning_count = 0
        suite_info_count = 0
        suite_metainfo_count = 0

        for component in suite['components']:
            issue_summaries = dict()
            mdata_summaries = dict()
            export_dir_section = os.path.join(self._export_dir, "html", suite_name, component)
            export_dir_issues = os.path.join(export_dir_section, "issues")
            export_dir_metainfo = os.path.join(export_dir_section, "metainfo")

            error_count = 0
            warning_count = 0
            info_count = 0
            metainfo_count = 0

            hint_pages = dict()
            cpt_pages = dict()

            for arch in suite['architectures']:
                pkglist = self._get_packages_for(suite_name, component, arch)

                for pkg in pkglist:
                    pkid = pkg.pkid

                    maintainer = None
                    if pkg:
                        maintainer = pkg.maintainer
                    if not maintainer:
                        maintainer = "Unknown"

                    #
                    # Data processing hints
                    #
                    hints_list = self._cache.get_hints(pkid)
                    if hints_list:
                        hints_list = yaml.safe_load_all(hints_list)
                        for hdata in hints_list:
                            pkg_name = hdata['Package']
                            pkg_id = hdata.get('PackageID')
                            if not pkg_id:
                                pkg_id = pkg_name
                            if not issue_summaries.get(maintainer):
                                issue_summaries[maintainer] = dict()

                            hints_raw = hdata.get('Hints', list())

                            # expand all hints to show long descriptions
                            errors = list()
                            warnings = list()
                            infos = list()

                            for hint in hints_raw:
                                ehint = self._expand_hint(hint)
                                severity = ehint['severity']
                                if severity == "info":
                                    infos.append(ehint)
                                elif severity == "warning":
                                    warnings.append(ehint)
                                else:
                                    errors.append(ehint)

                            if not hint_pages.get(pkg_name):
                                hint_pages[pkg_name] = list()

                            # we fold multiple architectures with the same issues into one view
                            pkid_noarch = pkg_id
                            if "/" in pkg_id:
                                pkid_noarch = pkg_id[:pkg_id.rfind("/")]

                            pcid = ""
                            if hdata.get('ID'):
                                pcid = "%s: %s" % (pkid_noarch, hdata.get('ID'))
                            else:
                                pcid = pkid_noarch

                            page_data = {'identifier': pcid, 'errors': errors, 'warnings': warnings, 'infos': infos, 'archs': [arch]}
                            try:
                                l = hint_pages[pkg_name]
                                index = next(i for i, v in enumerate(l) if equal_dicts(v, page_data, ['archs']))
                                hint_pages[pkg_name][index]['archs'].append(arch)
                            except StopIteration:
                                hint_pages[pkg_name].append(page_data)

                                # add info to global issue count
                                error_count += len(errors)
                                warning_count += len(warnings)
                                info_count += len(infos)

                                # add info for global index
                                if not issue_summaries[maintainer].get(pkg_name):
                                    issue_summaries[maintainer][pkg_name] = {'error_count': len(errors), 'warning_count': len(warnings), 'info_count': len(infos)}


                    #
                    # Component metadata
                    #
                    cptgids = self._cache.get_cpt_gids_for_pkg(pkid)
                    if cptgids:
                        for cptgid in cptgids:
                            mdata = self._cache.get_metadata(cptgid)
                            if not mdata:
                                log.error("Package '%s' refers to missing component with gid '%s'" % (pkid, cptgid))
                                continue
                            mdata = yaml.safe_load(mdata)

                            pkg_name = mdata.get('Package')
                            if not pkg_name:
                                # we probably hit the header
                                continue
                            if not mdata_summaries.get(maintainer):
                                mdata_summaries[maintainer] = dict()


                            # ugly hack to have the screenshot entries linked
                            #if mdata.get('Screenshots'):
                            #    sshot_baseurl = os.path.join(self._dep11_url, component)
                            #    for i in range(len(mdata['Screenshots'])):
                            #        url = mdata['Screenshots'][i]['source-image']['url']
                            #        url = "<a href=\"%s\">%s</a>" % (os.path.join(sshot_baseurl, url), url)
                            #        mdata['Screenshots'][i]['source-image']['url'] = Markup(url)
                            #        thumbnails = mdata['Screenshots'][i]['thumbnails']
                            #        for j in range(len(thumbnails)):
                            #            url = thumbnails[j]['url']
                            #            url = "<a href=\"%s\">%s</a>" % (os.path.join(sshot_baseurl, url), url)
                            #            thumbnails[j]['url'] = Markup(url)
                            #        mdata['Screenshots'][i]['thumbnails'] = thumbnails


                            mdata_yml = dict_to_dep11_yaml(mdata)
                            mdata_yml = self._highlight_yaml(mdata_yml)
                            cid = mdata.get('ID')

                            # try to find an icon for this component (if it's a GUI app)
                            icon_url = None
                            if mdata['Type'] == 'desktop-app' or mdata['Type'] == "web-app":
                                icon_name = mdata['Icon'].get("cached")
                                if icon_name:
                                    icon_fname = os.path.join(component, cptgid, "icons", "64x64", icon_name)
                                    if os.path.isfile(os.path.join(media_dir, icon_fname)):
                                        icon_url = os.path.join(self._dep11_url, icon_fname)
                                    else:
                                        icon_url = noimage_url
                                else:
                                    icon_url = noimage_url
                            else:
                                icon_url = os.path.join(self._html_url, "static", "img", "cpt-nogui.png")

                            if not cpt_pages.get(pkg_name):
                                cpt_pages[pkg_name] = list()

                            page_data = {'cid': cid, 'mdata': mdata_yml, 'icon_url': icon_url, 'archs': [arch]}
                            try:
                                l = cpt_pages[pkg_name]
                                index = next(i for i, v in enumerate(l) if equal_dicts(v, page_data, ['archs']))
                                cpt_pages[pkg_name][index]['archs'].append(arch)
                            except StopIteration:
                                cpt_pages[pkg_name].append(page_data)

                                # increase valid metainfo count
                                metainfo_count += 1

                            # check if we had this package, and add to summary
                            pksum = mdata_summaries[maintainer].get(pkg_name)
                            if not pksum:
                                pksum = dict()

                            if pksum.get('cids'):
                                if not cid in pksum['cids']:
                                    pksum['cids'].append(cid)
                            else:
                                pksum['cids'] = [cid]

                            mdata_summaries[maintainer][pkg_name] = pksum


            #
            # Summary and HTML writing
            #

            log.info("Rendering HTML pages for suite '%s/%s'" % (suite_name, component))

            # remove old HTML pages
            shutil.rmtree(export_dir_section, ignore_errors=True)

            # now write the HTML pages with the previously collected & transformed issue data
            for pkg_name, entry_list in hint_pages.items():
                # render issues page
                self.render_template("issues_page.html", export_dir_issues, "%s.html" % (pkg_name),
                        package_name=pkg_name, entries=entry_list, suite=suite_name, section=component)

            # render page with all components found in a package
            for pkg_name, cptlist in cpt_pages.items():
                # render metainfo page
                self.render_template("metainfo_page.html", export_dir_metainfo, "%s.html" % (pkg_name),
                        package_name=pkg_name, cpts=cptlist, suite=suite_name, section=component)

            # Now render our issue index page
            self.render_template("issues_index.html", export_dir_issues, "index.html",
                        package_summaries=issue_summaries, suite=suite_name, section=component)

            # ... and the metainfo index page
            self.render_template("metainfo_index.html", export_dir_metainfo, "index.html",
                        package_summaries=mdata_summaries, suite=suite_name, section=component)


            validate_result = "Validation was not performed."
            d_fname = os.path.join(dep11_minfodir, suite_name, component, "Components-%s.yml.gz" % (arch))
            if os.path.isfile(d_fname):
                # do format validation
                validator = DEP11Validator()
                ret = validator.validate_file(d_fname)
                if ret:
                    validate_result = "No errors found."
                else:
                    validate_result = ""
                    for issue in validator.issue_list:
                        validate_result += issue.replace("FATAL", "<strong>FATAL</strong>")+"<br/>\n"

            # sum up counts for suite statistics
            suite_metainfo_count += metainfo_count
            suite_error_count += error_count
            suite_warning_count += warning_count
            suite_info_count += info_count

            # add current statistics to the statistics database
            stats.add_data(suite_name, component, metainfo_count, error_count, warning_count, info_count)

            # calculate statistics for this component
            count = metainfo_count + error_count + warning_count + info_count
            valid_perc = 100/count*metainfo_count if count > 0 else 0
            error_perc = 100/count*error_count if count > 0 else 0
            warning_perc = 100/count*warning_count if count > 0 else 0
            info_perc = 100/count*info_count if count > 0 else 0

            # Render our overview page
            self.render_template("section_overview.html", export_dir_section, "index.html",
                        suite=suite_name, section=component, valid_percentage=valid_perc,
                        error_percentage=error_perc, warning_percentage=warning_perc, info_percentage=info_perc,
                        metainfo_count=metainfo_count, error_count=error_count, warning_count=warning_count,
                        info_count=info_count, validate_result=validate_result)


        # calculate statistics for this suite
        count = suite_metainfo_count + suite_error_count + suite_warning_count + suite_info_count
        valid_perc = 100/count*suite_metainfo_count if count > 0 else 0
        error_perc = 100/count*suite_error_count if count > 0 else 0
        warning_perc = 100/count*suite_warning_count if count > 0 else 0
        info_perc = 100/count*suite_info_count if count > 0 else 0

        # Render archive components index/overview page
        self.render_template("sections_index.html", export_dir, "index.html",
                        sections=suite['components'], suite=suite_name, valid_percentage=valid_perc,
                        error_percentage=error_perc, warning_percentage=warning_perc, info_percentage=info_perc,
                        metainfo_count=suite_metainfo_count, error_count=suite_error_count, warning_count=suite_warning_count,
                        info_count=suite_info_count)

        # plot graphs
        stats.plot_graphs(os.path.join(export_dir, "stats"))

        # Copy the static files
        target_static_dir = os.path.join(self._export_dir, "html", "static")
        shutil.rmtree(target_static_dir, ignore_errors=True)
        shutil.copytree(os.path.join(self._template_dir, "static"), target_static_dir)
