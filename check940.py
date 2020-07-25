#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=4:
# vim: ai:
# vim: shiftwidth=4:

import psycopg2, sys, os.path

def parse_arguments():
    if len(sys.argv) == 1:
        print("Usage: provide the file of bib id's to check, e.g. $ check940.py deletes.txt ")
        exit(1)

    filename = sys.argv[1]

    if not os.path.isfile(filename):
        print("Not a valid file: ", filename)
        exit(1)
    else:
        return filename

def get_list_of_ids_from_file(filename):
    ids = set()
    with open(filename, 'rb') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                bibid = int(line)
            except ValueError:
                print('Bad input - %s' % (line,))
                continue
            ids.add(bibid)
    return ids

def which_ids_have_tag(ids, cur, tag = '940'):
    """

    :type ids: set
    :type cur: psycopg2.extensions.connection
    :param tag: str
    :return: set
    """
    cur.execute("SELECT record from metabib.real_full_rec WHERE tag = '940';")
    ids_having_tag = set()
    for record in cur:
        ids_having_tag.add(record[0])

    oh_no = ids.intersection(ids_having_tag)
    return oh_no


def main():
    pass

if __name__ == "__main__":
    from marcaroni import db

    filename = parse_arguments()
    ids = get_list_of_ids_from_file(filename)

    conn = db.connect()
    cur = conn.cursor()

    found940 = False

    oh_no = which_ids_have_tag(ids, cur)

    if len(oh_no):
        found940 = True
        print(oh_no)

    if found940:
        print("HALT! THERE BE PURCHASES HERE.")
        exit(1)

    main()
    cur.close()
    conn.close()
    exit(0)