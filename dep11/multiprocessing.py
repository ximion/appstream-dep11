#!/usr/bin/env python
#
# Copyright (c) 2014-2015 Matthias Klumpp <mak@debian.org>
#                    2011 Ansgar Burchardt <ansgar@debian.org>
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

from multiprocessing.pool import Pool
from signal import signal, SIGHUP, SIGTERM, SIGPIPE, SIGALRM

__all__ = []

PROC_STATUS_SUCCESS      = 0  # Everything ok
PROC_STATUS_EXCEPTION    = 1  # An exception was caught
PROC_STATUS_SIGNALRAISED = 2  # A signal was generated
PROC_STATUS_MISCFAILURE  = 3  # Process specific error; see message

__all__.extend(['PROC_STATUS_SUCCESS',      'PROC_STATUS_EXCEPTION',
                'PROC_STATUS_SIGNALRAISED', 'PROC_STATUS_MISCFAILURE'])

class SignalException(Exception):
    def __init__(self, signum):
        self.signum = signum

    def __str__(self):
        return "<SignalException: %d>" % self.signum

__all__.append('SignalException')

def signal_handler(signum, info):
    raise SignalException(signum)

def _func_wrapper(func, *args, **kwds):
    # We need to handle signals to avoid hanging
    signal(SIGHUP, signal_handler)
    signal(SIGTERM, signal_handler)
    signal(SIGPIPE, signal_handler)
    signal(SIGALRM, signal_handler)

    # We expect our callback function to return:
    # (status, messages)
    # Where:
    #  status is one of PROC_STATUS_*
    #  messages is a string used for logging
    try:
        return (func(*args, **kwds))
    except SignalException as e:
        return (PROC_STATUS_SIGNALRAISED, e.signum)
    except Exception as e:
        return (PROC_STATUS_EXCEPTION, str(e))

class ExtractorProcessPool(Pool):
    def __init__(self, *args, **kwds):
        Pool.__init__(self, *args, **kwds)

    def apply_async(self, func, args=(), kwds={}, callback=None):
        wrapper_args = list(args)
        wrapper_args.insert(0, func)
        Pool.apply_async(self, _func_wrapper, wrapper_args, kwds, callback=callback)

__all__.append('ExtractorProcessPool')
