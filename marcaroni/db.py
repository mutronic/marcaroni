#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

import psycopg2, sys, os.path
from pathlib import Path
import configparser

def read_in_config():
    config = configparser.ConfigParser()
    # Load config file.
    config_path = os.path.join(Path.home(), '.marcaroni.ini')
    found = config.read(config_path)
    if len(found) == 0:
        print("No config files were found. Please place one in your home directory called .marcaroni.ini. See sample file"
              " for syntax.")
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

def connect():
    host, dbname, user, password = read_in_config()
    conn = psycopg2.connect(host=host, dbname=dbname, user=user, password=password)
    print('Connected to the database.')
    return conn