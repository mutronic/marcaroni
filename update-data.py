#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

import psycopg2, sys, os.path
from pathlib import Path
import configparser


def read_in_config():
    # Load config file.
    configpath = os.path.join(Path.home(), '.marcaroni.ini')
    config = configparser.ConfigParser()
    found = config.read(configpath)
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


host, dbname, user, password = read_in_config()
conn = psycopg2.connect(host=host, dbname=dbname, user=user, password=password)
cur = conn.cursor()


output = open('bib-data.txt', 'w')
output.write('isbn,id,source\n')
errors = open('shitty-isbns.txt','w')

#cur.copy_expert("COPY (SELECT bre.id, bre.source, rfr.value FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND rfr.tag = '020' AND rfr.subfield in ('a','z') and bre.source is not NULL) TO STDOUT WITH CSV HEADER", data_dictionary)
cur.execute("SELECT bre.id, bre.source, rfr.value FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND rfr.tag = '020' AND rfr.subfield in ('a','z') and bre.source is not NULL")

for row in cur:
  cleaned = row[2].strip()
  isbn = cleaned.split(' ')[0]
  isbn = isbn.strip('-')
  isbn = isbn.split('ü')[0] ## Delete me when umlauts are fixed
  isbn = isbn.split('(')[0]
  isbn = isbn.split('\\')[0]
  ## If ISBN is the wrong length, warn but don't break
  if len(isbn) != 10 and len(isbn) != 13:
    #print("We probably have not found a good isbn here: " + cleaned)
    errors.write(','.join(map(str,row)))
    errors.write('\n')
  ## Only consider matchable isbns strings that are between 9 and 14 chars.
  if len(isbn) > 8 and len(isbn) < 15:
    output.write(','.join((str(isbn),str(row[0]),str(row[1]))))
    output.write('\n')

exit()
