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
import tarfile
import glob
import shutil
import traceback
from argparse import ArgumentParser
import multiprocessing as mp
import logging as log

from dep11 import MetadataExtractor, DataCache, build_cpt_global_id, build_pkg_id
from dep11.component import DEP11Component, get_dep11_header, dict_to_dep11_yaml
from dep11.iconfinder import ContentsListIconFinder
from dep11.utils import get_data_dir, read_packages_dict_from_file, load_generator_config
from dep11.hints import get_hint_tag_info
from dep11.reportgenerator import ReportGenerator


def safe_move_file(old_fname, new_fname):
    if not os.path.isfile(old_fname):
        return
    if os.path.isfile(new_fname):
        os.remove(new_fname)
    os.rename(old_fname, new_fname)


def extract_metadata(mde, sn, pkgname, version, arch, package_fname):
    # we're now in a new process and can (re)open a LMDB connection
    mde.reopen_cache()
    cpts = mde.process(pkgname, version, arch, package_fname)

    msgtxt = "Processed: %s (%s/%s), found %i" % (pkgname, sn, arch, len(cpts))
    return msgtxt


class DEP11Generator:
    def __init__(self):
        pass


    def initialize(self, dep11_dir):
        dep11_dir = os.path.abspath(dep11_dir)

        conf = load_generator_config(dep11_dir)
        if not conf:
            return False

        self._dep11_url = conf.get("MediaBaseUrl")
        self._icon_sizes = conf.get("IconSizes")
        if not self._icon_sizes:
            self._icon_sizes = ["128x128", "64x64"]

        self._archive_root = conf.get("ArchiveRoot")

        cache_dir = os.path.join(dep11_dir, "cache")
        if conf.get("CacheDir"):
            cache_dir = conf.get("CacheDir")

        self._export_dir = os.path.join(dep11_dir, "export")
        if conf.get("ExportDir"):
            self._export_dir = conf.get("ExportDir")

        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        if not os.path.exists(self._export_dir):
            os.makedirs(self._export_dir)

        self._suites_data = conf['Suites']

        self._distro_name = conf.get("DistroName")
        if not self._distro_name:
            self._distro_name = "Debian"

        # the RepositoryName property is only interesting for
        # 3rd-party repositories using this generator, which don't want
        # to conflict with the main distro repository data.
        self._repo_name = conf.get("RepositoryName")
        if not self._repo_name:
            self._repo_name = self._distro_name

        # initialize our on-disk metadata pool
        self._cache = DataCache(self._get_media_dir())
        ret = self._cache.open(cache_dir)

        os.chdir(dep11_dir)
        return ret


    def _get_media_dir(self):
        mdir = os.path.join(self._export_dir, "media")
        if not os.path.exists(mdir):
            os.makedirs(mdir)
        return mdir


    def _get_packages_for(self, suite, component, arch):
        return read_packages_dict_from_file(self._archive_root, suite, component, arch).values()


    def make_icon_tar(self, suitename, component, pkglist):
        '''
         Generate icons-%(size).tar.gz
        '''
        dep11_mediadir = self._get_media_dir()
        names_seen = set()
        tar_location = os.path.join(self._export_dir, "data", suitename, component)

        size_tars = dict()

        for pkg in pkglist:
            pkid = build_pkg_id(pkg['name'], pkg['version'], pkg['arch'])

            gids = self._cache.get_cpt_gids_for_pkg(pkid)
            if not gids:
                # no component global-ids == no icons to add to the tarball
                continue

            for gid in gids:
                for size in self._icon_sizes:
                    icon_location_glob = os.path.join (dep11_mediadir, component, gid, "icons", size, "*.png")

                    tar = None
                    if size not in size_tars:
                        icon_tar_fname = os.path.join(tar_location, "icons-%s.tar.gz" % (size))
                        size_tars[size] = tarfile.open(icon_tar_fname+".new", "w:gz")
                    tar = size_tars[size]

                    for filename in glob.glob(icon_location_glob):
                        icon_name = os.path.basename(filename)
                        if size+"/"+icon_name in names_seen:
                            continue
                        tar.add(filename, arcname=icon_name)
                        names_seen.add(size+"/"+icon_name)

        for tar in size_tars.values():
            tar.close()
            # FIXME Ugly....
            safe_move_file(tar.name, tar.name.replace(".new", ""))


    def process_suite(self, suite_name):
        '''
        Extract new metadata for a given suite.
        '''

        suite = self._suites_data.get(suite_name)
        if not suite:
            log.error("Suite '%s' not found!" % (suite_name))
            return False

        dep11_mediadir = self._get_media_dir()

        # We need 'forkserver' as startup method to prevent deadlocks on join()
        # Something in the extractor is doing weird things, makes joining impossible
        # when using simple fork as startup method.
        mp.set_start_method('forkserver')

        for component in suite['components']:
            all_cpt_pkgs = list()
            for arch in suite['architectures']:
                pkglist = self._get_packages_for(suite_name, component, arch)

                # compile a list of packages that we need to look into
                pkgs_todo = dict()
                for pkg in pkglist:
                    pkid = build_pkg_id(pkg['name'], pkg['version'], pkg['arch'])

                    # check if we scanned the package already
                    if self._cache.package_exists(pkid):
                        continue
                    pkgs_todo[pkid] = pkg

                # set up metadata extractor
                icon_theme = suite.get('useIconTheme')
                iconf = ContentsListIconFinder(suite_name, component, arch, self._archive_root, icon_theme)
                mde = MetadataExtractor(suite_name,
                                component,
                                self._icon_sizes,
                                self._cache,
                                iconf)

                # Multiprocessing can't cope with LMDB open in the cache,
                # but instead of throwing an error or doing something else
                # that makes debugging easier, it just silently skips each
                # multprocessing task. Stupid thing.
                # (remember to re-open the cache later)
                self._cache.close()

                # set up multiprocessing
                with mp.Pool(maxtasksperchild=24) as pool:
                    def handle_results(message):
                        log.info(message)

                    def handle_error(e):
                        traceback.print_exception(type(e), e, e.__traceback__)
                        log.error(str(e))
                        pool.terminate()
                        sys.exit(5)

                    log.info("Processing %i packages in %s/%s/%s" % (len(pkgs_todo), suite_name, component, arch))
                    for pkid, pkg in pkgs_todo.items():
                        package_fname = os.path.join (self._archive_root, pkg['filename'])
                        if not os.path.exists(package_fname):
                            log.warning('Package not found: %s' % (package_fname))
                            continue
                        pool.apply_async(extract_metadata,
                                    (mde, suite_name, pkg['name'], pkg['version'], pkg['arch'], package_fname),
                                    callback=handle_results, error_callback=handle_error)
                    pool.close()
                    pool.join()

                # reopen the cache, we need it
                self._cache.reopen()

                hints_dir = os.path.join(self._export_dir, "hints", suite_name, component)
                if not os.path.exists(hints_dir):
                    os.makedirs(hints_dir)
                dep11_dir = os.path.join(self._export_dir, "data", suite_name, component)
                if not os.path.exists(dep11_dir):
                    os.makedirs(dep11_dir)

                # now write data to disk
                hints_fname = os.path.join(hints_dir, "DEP11Hints_%s.yml.gz" % (arch))
                data_fname = os.path.join(dep11_dir, "Components-%s.yml.gz" % (arch))

                hints_f = gzip.open(hints_fname+".new", 'wb')
                data_f = gzip.open(data_fname+".new", 'wb')

                dep11_header = get_dep11_header(self._repo_name, suite_name, component, os.path.join(self._dep11_url, component), suite.get('dataPriority', 0))
                data_f.write(bytes(dep11_header, 'utf-8'))

                for pkg in pkglist:
                    pkid = build_pkg_id(pkg['name'], pkg['version'], pkg['arch'])
                    data = self._cache.get_metadata_for_pkg(pkid)
                    if data:
                        data_f.write(bytes(data, 'utf-8'))
                    hint = self._cache.get_hints(pkid)
                    if hint:
                        hints_f.write(bytes(hint, 'utf-8'))

                data_f.close()
                safe_move_file(data_fname+".new", data_fname)

                hints_f.close()
                safe_move_file(hints_fname+".new", hints_fname)

                all_cpt_pkgs.extend(pkglist)

            # create icon tarball
            self.make_icon_tar(suite_name, component, all_cpt_pkgs)

            log.info("Completed metadata extraction for suite %s/%s" % (suite_name, component))


    def expire_cache(self):
        pkgids = set()
        for suite_name in self._suites_data:
            suite = self._suites_data[suite_name]
            for component in suite['components']:
                for arch in suite['architectures']:
                    pkglist = self._get_packages_for(suite_name, component, arch)
                    for pkg in pkglist:
                        pkid = build_pkg_id(pkg['name'], pkg['version'], pkg['arch'])
                        pkgids.add(pkid)

        # clean cache
        oldpkgs = self._cache.get_packages_not_in_set(pkgids)
        for pkid in oldpkgs:
            pkid = str(pkid, 'utf-8')
            self._cache.remove_package(pkid)

        # ensure we don't leave cruft, drop orphaned components (cpts w/o pkg)
        self._cache.remove_orphaned_components()
        # drop orphaned media (media w/o registered cpt)
        self._cache.remove_orphaned_media()


    def remove_processed(self, suite_name):
        '''
        Delete information about processed packages, to reprocess them later.
        '''

        suite = self._suites_data.get(suite_name)
        if not suite:
            log.error("Suite '%s' not found!" % (suite_name))
            return False

        for component in suite['components']:
            all_cpt_pkgs = list()
            for arch in suite['architectures']:
                pkglist = self._get_packages_for(suite_name, component, arch)

                for pkg in pkglist:
                    package_fname = os.path.join (self._archive_root, pkg['filename'])
                    pkid = build_pkg_id(pkg['name'], pkg['version'], pkg['arch'])

                    # we ignore packages without any interesting metadata here
                    if self._cache.is_ignored(pkid):
                        continue
                    if not self._cache.package_exists(pkid):
                        continue

                    self._cache.remove_package(pkid)

        # drop all components which don't have packages
        self._cache.remove_orphaned_components()


    def forget_package(self, pkid):
        '''
        Delete all information about a single package in the cache.
        '''

        if not self._cache.package_exists(pkid):
            print("Package with ID '%s' does not exist." % (pkid))
            return

        self._cache.remove_package(pkid)

        # drop all components which don't have packages
        self._cache.remove_orphaned_components()


def main():
    """Main entry point of generator"""

    apt_pkg.init()

    parser = ArgumentParser(description="Generate DEP-11 metadata from Debian packages.")
    parser.add_argument('subcommand', help="The command that should be executed.")
    parser.add_argument('parameters', nargs='*', help="Parameters for the subcommand.")

    parser.usage = "\n"
    parser.usage += " process [CONFDIR] [SUITE]     - Process packages and extract metadata.\n"
    parser.usage += " cleanup [CONFDIR]             - Remove unused data from the cache and expire media.\n"
    parser.usage += " update-reports [CONFDIR] [SUITE]   - Re-generate the metadata and issue HTML pages and update statistics.\n"
    parser.usage += " remove-processed [CONFDIR] [SUITE] - Remove information about processed or failed components.\n"
    parser.usage += " forget [CONFDIR] [PKID]            - Forget a single package and data associated with it.\n"

    args = parser.parse_args()
    command = args.subcommand
    params = args.parameters

    # configure logging
    log_level = log.INFO
    if os.environ.get("DEBUG"):
        log_level = log.DEBUG
    log.basicConfig(format='%(asctime)s - %(levelname)s: %(message)s', level=log_level)

    if command == "process":
        if len(params) != 2:
            print("Invalid number of arguments: You need to specify a DEP-11 data dir and suite.")
            sys.exit(1)
        gen = DEP11Generator()
        ret = gen.initialize(params[0])
        if not ret:
            print("Initialization failed, can not continue.")
            sys.exit(2)

        gen.process_suite(params[1])

    elif command == "cleanup":
        if len(params) != 1:
            print("Invalid number of arguments: You need to specify a DEP-11 data dir.")
            sys.exit(1)
        gen = DEP11Generator()
        ret = gen.initialize(params[0])
        if not ret:
            print("Initialization failed, can not continue.")
            sys.exit(2)

        gen.expire_cache()

    elif command == "update-reports":
        if len(params) != 2:
            print("Invalid number of arguments: You need to specify a DEP-11 data dir and suite.")
            sys.exit(1)
        hgen = ReportGenerator()
        ret = hgen.initialize(params[0])
        if not ret:
            print("Initialization failed, can not continue.")
            sys.exit(2)

        hgen.update_reports(params[1])

    elif command == "remove-processed":
        if len(params) != 2:
            print("Invalid number of arguments: You need to specify a DEP-11 data dir and suite.")
            sys.exit(1)
        gen = DEP11Generator()
        ret = gen.initialize(params[0])
        if not ret:
            print("Initialization failed, can not continue.")
            sys.exit(2)

        gen.remove_processed(params[1])
    elif command == "forget":
        if len(params) != 2:
            print("Invalid number of arguments: You need to specify a DEP-11 data dir and package-id.")
            sys.exit(1)
        gen = DEP11Generator()
        ret = gen.initialize(params[0])
        if not ret:
            print("Initialization failed, can not continue.")
            sys.exit(2)

        gen.forget_package(params[1])
    else:
        print("Run with --help for a list of available command-line options!")
