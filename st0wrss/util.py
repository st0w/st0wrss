# ---*< st0wrss/util.py >*----------------------------------------------
# Copyright (C) 2014 st0w
#
# This module is part of st0w RSS Downloader and is released under the
# MIT License.  Please see the LICENSE file for details.
#
#
"""Utility routines

Created on Nov 15, 2014

"""
# ---*< Standard imports >*---------------------------------------------
from os.path import abspath, expanduser, isfile

# ---*< Third-party imports >*------------------------------------------

# ---*< Local imports >*------------------------------------------------

# ---*< Initialization >*-----------------------------------------------

# ---*< Code >*---------------------------------------------------------
def file_resolv(path, alt=None):
    """Resolves a dir as best as possible"""
    path = expanduser(path)

    if path[0] is not '/':
        # If path is relative, first check in alt, then abspath..lazy
        if isfile('%s/%s' % (alt, path)):
            path = '%s/%s' % (alt, path)
        else:
            path = abspath(path)

    return path


def build_message(dls=None, dupes=None, skipping=None, errs=None):
    """A simple function to format status email.. Use it or your own"""

    # Don't do anything if there's nothing to report
    if not dls and not dupes and not skipping and not errs:
        return None

    msg = """Downloading ::

%s

Dupes ::

%s

Skipping ::

%s

Errors ::

%s
    """ % ("\n".join(dls), "\n".join(dupes), "\n".join(skipping),
           "\n".join(errs))

    return msg

