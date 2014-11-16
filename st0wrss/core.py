# ---*< st0wrss/misc.py >*----------------------------------------------
# Copyright (C) 2014 st0w
#
# This module is part of st0w RSS Downloader and is released under the
# MIT License.  Please see the LICENSE file for details.
#
# pylint:disable=locally-disabled, invalid-name
"""Core routines for downloading RSS attachments

Created on Nov 9, 2014

Code that was once in separate scripts but now integrated in one place.
The class intentionally doesn't actually download or parse the feed, as
it's a lot more flexible if you code that part yourself.  This handles
the local management of torrent files.

"""
# ---*< Standard imports >*---------------------------------------------
import configparser
import errno
import os
import re
import sqlite3
import sys
import smtplib
import urllib.request, urllib.error, urllib.parse

# ---*< Third-party imports >*------------------------------------------
from bencodepy import decode

# ---*< Local imports >*------------------------------------------------
from st0wrss.util import file_resolv

# ---*< Initialization >*-----------------------------------------------
SMTP_SERVER = 'localhost'
SMTP_PORT = 25
DB_DIR = '~/.st0wrss'
DB_FILE = 'rss.db'
CONFIG_FILE = 'st0wrssrc'

# ---*< Code >*---------------------------------------------------------
class st0wRSS:
    """Class for handling all RSS-related routines

    I'm really not crazy about setting defaults this way, but I wanted
    to be sure it was possible to have defaults, be able to call
    __init__() without passing anything and get those defaults, accept
    the defaults set in the rc file, and finally to also pass specific
    values that always take precedence.  This seems to accomplish it,
    albeit clumsily.

    DB Schemia:
    url - string, URL to torrent

    """
    check_dupey = True
    mail_settings = {}
    """
    Values and defaults include:
    {
        'smtp_server': SMTP_SERVER,
        'smtp_port': SMTP_PORT,
        'to': None, # If you don't set this, mail won't get sent.
        'from': 'st0wrss@localhost',
        'from_name': 'st0wRSS Daemon 2.0'
    }
    """

    def __init__(self, mailto=None, smtp_server=None, smtp_port=None,
                 db_dir=None, db_file=None, config_file=None,
                 torrent_dir=None):
        """Basic setup routines for st0w RSS Downloader

        Verifies all logging/DB directories exist, will create files if they
        don't exist.

        db_dir - directory for DB and log files.. NOT where torrent
                 files go.
        mailto - E-mail address to send results to
        """
        # Resolve dir, load config
        db_dir = (os.path.abspath(os.path.expanduser(db_dir)) if db_dir
                  else os.path.abspath(os.path.expanduser(DB_DIR)))

        config_file = config_file if config_file else CONFIG_FILE

        config = configparser.ConfigParser()
        config_file = file_resolv(config_file, db_dir)
        config.read(config_file)

        options = config['options']
        db_file = db_file if db_file else options.get('db_file', DB_FILE)

        # Mail settings... 'to' does not have a default
        self.mail_settings['to'] = mailto if mailto else options.get('mailto')
        self.mail_settings['from'] = options.get('mailfrom',
                                                 'st0wrss@localhost')
        self.mail_settings['from_name'] = options.get('mailfrom_name',
                                                      'st0wRSS Daemon 2.0')
        self.mail_settings['smtp_server'] = (smtp_server if smtp_server else
                                             options.get('smtp_server',
                                                         SMTP_SERVER))
        self.mail_settings['smtp_port'] = (smtp_port if smtp_port else
                                           options.get('smtp_port', SMTP_PORT))

        # Since at this point we assume db_file and db_dir are set, use
        # them.
        if db_file[0] != '/': # yeah, so... this only works on *NIX
            db_file = '%s%s%s' % (db_dir, os.sep, db_file)

        dirs = config['dirs']
        if not dirs['file_dirs']:
            print('Config must contain section [dirs] with at at least one '
                  'directory in file_dirs to enable duplicate checking',
                  file=sys.stderr)
            self.check_dupey = False
        else:
            self.dupey_dirs = dirs['file_dirs'].split(':')

        self.torrent_dir = torrent_dir if torrent_dir else dirs.get(
            'torrent_dir')

        if not self.torrent_dir:
            raise ValueError('torrent_dir must either be specified in rc or '
                             'passed to st0wrss.__init__(). ')

        # Create data directory, if it doesn't exist
        try:
            os.makedirs(db_dir)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise

        # Open logfile
        try:
            self.logfile = open('%s/rss.log' % db_dir, 'a')
        except FileNotFoundError:
            print('Unable to open logfile %s/rss.log\n'
                  'Make sure directory exists and is writable.\n'
                  % db_dir, file=sys.stderr)
            raise

        self.db = sqlite3.connect(db_file)
        self.create_table()


    def start_process(self, url):
        """Processes a torrent, or skips if already done

        Attempts to create a record in the DB.  If successful, that
        means it hadn't been processed before.  So return true.
        If we hit the exception, it means an attempt was already made
        to process this torrent, so return false.

        url - `string` containing URL to torrent file

        returns `bool` true or false if already processed
        """
        process = True

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO dls (url, path) VALUES (?, ?)
            """, (url, url)) # URL as placeholder for path (has to be unique)
            self.db.commit()
        except sqlite3.IntegrityError:
            process = False

        return process


    def create_table(self):
        """Creates the SQLite table, if necessary"""
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dls(
                url TEXT PRIMARY KEY,
                timestamp INTEGER(4) NOT NULL DEFAULT (strftime('%s','now')),
                path TEXT UNIQUE NOT NULL,
                downloaded INTEGER(1) NOT NULL DEFAULT 0,
                finished INTEGER(1) NOT NULL DEFAULT 0
            )
        """)
        # select url,path,datetime(timestamp,'unixepoch'),datetime() from dls;
        self.db.commit() # Don't be scared to commit...


    def finished(self, message, from_name=None):
        """Closes open files and sends the final status e-mail"""

        # Close DB and logfile
        self.db.close()
        self.logfile.close()

        # Send status mail
        if message and self.mail_settings['to']:
            if not from_name:
                from_name = self.mail_settings['from_name']
            self.sendmail(self.mail_settings['from'], from_name,
                          self.mail_settings['to'], message)


    def skip_torrent(self, url):
        """Marks a torrent as processed without downloading it"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO dls (url, path, finished) VALUES (?, ?, 1)
            """, (url, url)) # URL as placeholder for path, has to be be unique
            self.db.commit()
        except sqlite3.IntegrityError:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE dls SET finished=1 WHERE url=?
            """, (url,))
            self.db.commit()


    def get_torrent(self, url):
        """Downloads a torrent file, if it hasn't already been d/led

        Note that this function does NOT check in the DB for existence!
        Verification of that should be done prior, by calling
        start_process().  This function assumes you know you want to
        try to download the torrent file, and only checks for existence
        on disk of the path specified in the torrent.  The reason for this
        is to allow for logic between checking if the URL was processed
        and actually downloading the torrent file, on a per-caller
        basis.  If these two steps were combined, every torrent would
        be downloaded from every tracker RSS feed every time this is
        called, which generates far too many useless, duplicate requests

        url - `string` with URL of the torrent file to get

        Returns `bool` indicating whether torrent was downloaded (true)
        or skipped due to pre-existence (false)
        """
        resp = urllib.request.urlopen(url)
        torrent = resp.read()
        torrent_data = decode(torrent)

        # Extract the base directory from the torrent file to check for
        # duplicates.
        #
        # Per the torrent spec, the 'name' field in multi-file
        # torrents is advised to contain the name of the directory
        # containing all of the data files.
        #
        # https://wiki.theory.org/BitTorrentSpecification
        torrent_path = torrent_data[b'info'][b'name'].decode(encoding='UTF-8')

        # Check incomplete and complete dirs for path
        # Slight TOCTOU race condition here...  But I don't care
        found = False
        if self.check_dupey:
            for d in self.dupey_dirs:
                if os.path.exists('%s%s%s' % (d, os.sep, torrent_path)):
                    found = True

        if not found:
            # Drop the torrent file into the torrent_dir
            fn = '%s%s%s.torrent' % (os.path.abspath(self.torrent_dir),
                                     os.sep,
                                     re.sub(r'[^\w\.\-]', '_', torrent_path))

            try:
                #pylint:disable=locally-disabled, bad-open-mode
                torfile = open(fn, 'xb')
                torfile.write(torrent)
                torfile.close()
            except FileExistsError:
                found = True

        if found:
            # We found either the torrent or the path, so mark it as
            # processed for the future
            self.skip_torrent(url)
            return False
        else:
            # It was new, so update the DB to reflect success
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE dls SET path=?, downloaded=1, finished=1
                WHERE url=?
            """, (torrent_path, url))
            self.db.commit()
            return True


    def sendmail(self, from_addr, from_name, to_addr, body):
        """Sends a status e-mail via particular server

        from_addr - address to send message from

        sendmail('st0w@sol.whatbox.ca', 'TR Daemon',
        """
        msg = """From: "%s" <%s>
To: You <%s>
Subject: %s Notification

%s""" % (from_name, from_addr, to_addr, from_name, body)
        smtp = smtplib.SMTP(self.mail_settings['smtp_server'],
                            self.mail_settings['smtp_port'])
        smtp.sendmail(self.mail_settings['from'], [self.mail_settings['to'],],
                      msg)
        smtp.quit()


