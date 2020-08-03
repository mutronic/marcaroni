#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

import psycopg2, sys, os.path
from pathlib import Path
import configparser

from typing import Iterator, Optional
import io


def read_in_config(test = False):
    ## Defaults to conf/.marcaroni.ini
    ## Then falls back to ~/.marcaroni.ini
    ## Then looks in this folder
    ## If passed 'test' as true, look for marcaroni.test.ini.
    if test:
        config_filename = '.marcaroni.test.ini'
    else:
        config_filename = '.marcaroni.ini'

    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), '../conf', config_filename))
    if len(config.sections()) == 0:
        config_path = os.path.join(Path.home(), config_filename)
        config.read(config_path)
        if len(config.sections()) == 0:
            config.read(config_filename)
            if len(config.sections()) == 0:
                print("Config file not found. Please place one in the conf/ directory of this program, or your home directory, named .marcaroni.ini. See sample file for syntax.")
                sys.exit(1)

    if not config.has_section('database'):
        print("Database section not found in config file.")
        sys.exit(1)

    database = config['database']

    for key in ('host', 'dbname', 'user', 'password'):
        if key not in database:
            print("Missing key [%s]" % (key,))
            sys.exit(1)

    return database['host'], database['dbname'], database['user'], database['password']

def connect(test = False):
    host, dbname, user, password = read_in_config(test)
    try:
        conn = psycopg2.connect(host=host, dbname=dbname, user=user, password=password, connect_timeout = 10)
        print('Connected to the database: %s@%s' % (dbname, host))
    except Exception as e:
        print("Error trying to connect to database. ", e)
        exit(1)
    else:
        return conn

## This StringIteratorIO class is from Haki Benita
## https://hakibenita.com/fast-load-data-python-postgresql

class StringIteratorIO(io.TextIOBase):
    def __init__(self, iter: Iterator[str]):
        self._iter = iter
        self._buff = ''

    def readable(self) -> bool:
        return True

    def _read1(self, n: Optional[int] = None) -> str:
        while not self._buff:
            try:
                self._buff = next(self._iter)
            except StopIteration:
                break
        ret = self._buff[:n]
        self._buff = self._buff[len(ret):]
        return ret

    def read(self, n: Optional[int] = None) -> str:
        line = []
        if n is None or n < 0:
            while True:
                m = self._read1()
                if not m:
                    break
                line.append(m)
        else:
            while n > 0:
                m = self._read1(n)
                if not m:
                    break
                n -= len(m)
                line.append(m)
        return ''.join(line)

    def readline(self):
        ret = self._read1()
        return ret