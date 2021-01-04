#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

from pymarc import MARCReader, XMLWriter
from io import BytesIO
import re
import sys
from datetime import datetime, timedelta
from marcaroni import db
import optparse
import psycopg2.extras
import os

def parse_config():
    parser = optparse.OptionParser(usage="%prog [options] [INPUT_FILE]")
    parser.add_option("--init", dest="init", default=False, action="store_true",
                      help="Initialize the database.")
    parser.add_option("-t", "--test", dest="test", default=False, action="store_true",
                      help="Use the test database config conf/.marcaroni.test.ini")
    parser.add_option("-q", "--quiet", dest="silent", default=False, action="store_true",
                      help="Quiet mode: process without interaction. DANGER use at your own risk.")
    parser.add_option("-s", "--source", dest="source",
                      help="Numerical id of bib source for this batch. If empty, will prompt for this.")
    parser.add_option("-u", "--user", dest="user_id", default='1',
                      help="User id of the record creator and editor. [default: %default]")
    opts, args = parser.parse_args()
    return opts.init, opts.source, opts.test, opts.silent, opts.user_id, args[0]

def load_marc_reader(filename):
    try:
        handler = open(filename, "rb")
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
    except Exception as e:
        print("Error loading marc handler")
        print("Exception: %s" % str(e))
        sys.exit(1)
    else:
        return reader

def marc_record_to_xml_string(record):
    b = BytesIO()
    writer = XMLWriter(b)
    writer.write(record)
    writer.close(close_fh=False)

    # Transform record from bytes to string.
    b.seek(0,0)
    bytestr = b.read()
    marc = bytestr.decode('UTF-8')

    # Remove the XML declaration and collection stuff.
    marc = re.sub(r'^.*<collection[^>]*>','',marc)
    marc = re.sub(r'</collection>$','',marc)
    # Remove tab characters.
    marc = re.sub(r'\t','',marc)

    # Verify cleaning worked:
    if not marc.startswith('<record'):
        print("Error: record failed to create clean XML.")
        return False
    else:
        return marc

def copy_marc_into_staging(conn, reader):
    with conn.cursor() as cursor:
        record_string_iterator = db.StringIteratorIO(((marc_record_to_xml_string(record)) + '\n'
                                                       for record in reader))
        cursor.copy_from(record_string_iterator,'public.custom_insert_staging_test', sep='\t', columns=['marc'])
    conn.commit()

def push_staging_to_bre_simple(conn):
    with conn.cursor() as cursor:

        cursor.execute("SELECT id FROM public.custom_insert_staging_test WHERE not finished;")
        row_ids = cursor.fetchall()

        cursor.execute("PREPARE stmt AS UPDATE public.custom_insert_staging_test SET finished = TRUE where id = $1;")
        psycopg2.extras.execute_batch(cursor,"EXECUTE stmt (%s)", row_ids)
        cursor.execute("DEALLOCATE stmt")
    conn.commit()


def insert_staged_records_to_biblio_record_entry(conn, bib_source, user_id, silent=True):
    with conn.cursor() as cursor:
        ## Get the rows to do
        cursor.execute("SELECT id FROM public.custom_insert_staging_test WHERE not finished;")
        row_ids = cursor.fetchall()
        if not silent:
            print(str(len(row_ids)) + " records to create and mark done.")

        ## Update and set as done.
        cursor.execute("PREPARE stmt AS "
                       "WITH ins AS ("
                       "    INSERT INTO biblio.record_entry (marc, creator, editor, source, last_xact_id) "
                       "    SELECT marc, %s, %s, %s, pg_backend_pid() || '.' || extract(epoch from now()) "
                       "    FROM public.custom_insert_staging_test where id = $1"
                       "    RETURNING id"
                       ") "
                       "UPDATE public.custom_insert_staging_test set finished = TRUE "
                       "    WHERE id = $1 "
                       "    AND EXISTS (SELECT 1 from ins)"
                       , (user_id, user_id, bib_source))

        psycopg2.extras.execute_batch(cursor,"EXECUTE stmt (%s)", row_ids)
        cursor.execute("DEALLOCATE stmt")
    conn.commit()

# TODO: Change the table name for the whole script.
def flossme(conn):
    with conn.cursor() as cursor:
        ## Create table
        cursor.execute("CREATE TABLE staging_records_import (id BIGSERIAL, dest BIGINT, marc TEXT);")
        conn.commit()

def unfinished_records_in_staging(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT count(id) from public.custom_insert_staging_test WHERE not finished")
        count = cursor.fetchone()[0]
    return count

def main():
    pass

if __name__ == '__main__':
    init, bib_source, test, silent, user_id, filename = parse_config()

    # Prepare the database connection.
    if not silent:
        print("Connecting to database...")
    conn = db.connect(test)

    # Are there staged records that have not been finished?
    count = unfinished_records_in_staging(conn)

    # No sources of input
    if count == 0 and not filename:
        print("No records are ready and no file was provided.")
        exit(0)

    # Possibly too many sources of input
    load_file = True
    if count > 0 and filename:
        response = input("There are [{}] unfinished records in the staging database that will be loaded if you continue. Do you want to also add the current file to these staged records? y or yes to add the file, n or no to skip the file and continue with the existing staged records. Anything else to cancel. [Y/n]".format(count,))
        if response in ('y','Y','yes','Yes'):
            load_file = True
        elif response in ('n','no','N','No'):
            load_file = False
        else:
            print("Invalid choice. Exiting.")
            exit(1)

    if not bib_source:
        bib_source = input("Please enter the number of the bib source:").strip()


    if load_file:
        if not silent:
            print("Processing file: [{}].".format(filename,))
        reader = load_marc_reader(filename)
        if not silent:
            print("Copying marc to staging database.")
            start_time = datetime.now()
        copy_marc_into_staging(conn, reader)
        if not silent:
            print("Records staged.")
            duration = datetime.now() - start_time
            print("Elapsed time: %s" % (str(duration),) )


    # PREPARE TO EXECUTE THE BIG RECORD LOAD
    count = unfinished_records_in_staging(conn)

    if not silent:
        print("Ready to insert records from the staging table:\n# RECORDS:\t{}\nBIB SOURCE:\t{}\nUSER ID:\t{}\n\n".format(count,bib_source, user_id))
        os.system('say "Ready to load records?"')
        if input("Insert staged records?? n or Ctrl+D to quit. [Y/n]") in ('n', 'no'):
            print("Exiting.")
            exit(1)
        print("Inserting staged records.")
        start_time = datetime.now()

    # PERFORM THE BATCH LOAD
    insert_staged_records_to_biblio_record_entry(conn, bib_source, user_id, silent)

    # REPORT ON THE LOAD.
    if not silent:
        duration = datetime.now() - start_time
        print("Elapsed time: %s" % (str(duration),) )

        count = unfinished_records_in_staging(conn)
        if count == 0:
            print("All staged records have been inserted.")
        else:
            print("There are still [{}] unfinished records in the staging database.".format(count,))

        # cursor.execute("INSERT INTO biblio.record_entry (marc, creator, editor, source, last_xact_id) SELECT marc, '1', '1', '2', pg_backend_pid() || '.' || extract(epoch from now()) FROM public.custom_insert_staging_test where id = %s;", (68327,))


main()

