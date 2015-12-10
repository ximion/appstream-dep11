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
import time
import logging as log
import datetime as dt
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from dep11 import DataCache


class StatsGenerator:
    def __init__(self, cache):
        self._cache = cache

    def add_data(self, suite_name, component, metainfo_count, error_count, warning_count, info_count):
        """ Add new statistical data to the database. """
        timestamp = int(time.time())

        data = list()
        data_stats = dict()
        data_stats['Suite'] = suite_name
        data_stats['Component'] = component
        data_stats['MetadataCount'] = metainfo_count
        data_stats['ErrorCount'] = error_count
        data_stats['WarningCount'] = warning_count
        data_stats['InfoCount'] = info_count
        data.append(data_stats)

        self._cache.set_stats(timestamp, yaml.safe_dump(data))

    def plot_graphs(self, out_dir):
        """ Plot graphs about the change of statistical data over time. """

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        # prepare our data for plotting
        data = dict()
        data_raw = self._cache.get_stats()
        for timestamp, raw in data_raw.items():
            doc = yaml.safe_load(raw)
            for entry in doc:
                suite = entry.get('Suite')
                component = entry.get('Component')
                if not suite or not component:
                    continue
                if not data.get(suite):
                    data[suite] = dict()
                sc = data[suite]
                if not sc.get(component):
                    data[suite][component] = dict()
                vals = data[suite][component]
                if not vals.get('mcount'):
                    vals['mcount'] = dict()
                if not vals.get('ecount'):
                    vals['ecount'] = dict()
                if not vals.get('wcount'):
                    vals['wcount'] = dict()
                if not vals.get('icount'):
                    vals['icount'] = dict()
                vals['mcount'][timestamp] = entry.get('MetadataCount')
                vals['ecount'][timestamp] = entry.get('ErrorCount')
                vals['wcount'][timestamp] = entry.get('WarningCount')
                vals['icount'][timestamp] = entry.get('InfoCount')

        dpi = 92
        for suite, cdata in data.items():
            for component, vals in cdata.items():
                # TODO: Think of a smarter way to set the figure size
                plt.figure(figsize=(1200/dpi, 500/dpi), dpi=dpi)
                locator = mdates.AutoDateLocator()
                formatter = mdates.AutoDateFormatter(locator, defaultfmt='%Y-%m-%d')
                formatter.scaled[1/(24.*60.)] = '%H:%M:%S'
                plt.gca().xaxis.set_major_formatter(formatter)
                plt.gca().xaxis.set_major_locator(locator)

                # NOTE: The "dates" variable should be the same for all issue hints, but in case we change that in future
                # (e.g. by adding another hint type), we calculate it individually here.
                dates = [dt.datetime.fromtimestamp(d) for d in vals['mcount'].keys()]
                plt.plot(dates, list(vals['mcount'].values()), color='green', linestyle='solid', marker='o')

                dates = [dt.datetime.fromtimestamp(d) for d in vals['ecount'].keys()]
                plt.plot(dates, list(vals['ecount'].values()), color='red', linestyle='solid', marker='o')

                dates = [dt.datetime.fromtimestamp(d) for d in vals['wcount'].keys()]
                plt.plot(dates, list(vals['wcount'].values()), color='orange', linestyle='solid', marker='o')

                dates = [dt.datetime.fromtimestamp(d) for d in vals['icount'].keys()]
                plt.plot(dates, list(vals['icount'].values()), color='cornflowerblue', linestyle='solid', marker='o')

                plt.gcf().autofmt_xdate()
                plt.savefig(os.path.join(out_dir, "%s-%s_stats.png" % (suite, component)), bbox_inches='tight')
                log.debug("Plot complete for %s/%s" % (suite, component))
