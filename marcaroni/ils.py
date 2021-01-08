#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=4:
# vim: ai:
# vim: shiftwidth=4:

import sys
import csv

from collections import namedtuple
# Rename this? KnownRecord? ExistingRecord?
Record = namedtuple('Record', ['id', 'source'])

class ILSBibData:
    def __init__(self):
        self.records_by_identifiers = {}

    def load_from_file(self, bib_data_file_name, match_field = None):
        with open(bib_data_file_name, 'r') as datafile:
            reader = csv.DictReader(datafile, delimiter=',')
            next(reader)  # skip header, which is 'identifier,id,source,tag,subfield'
            for row in reader:
                if match_field \
                        and row['tag'] != match_field:
                    continue
                identifier = row['identifier']
                record_tuple = Record(row['id'], row['source'])
                if identifier not in self.records_by_identifiers:
                    self.records_by_identifiers[identifier] = []
                self.records_by_identifiers[identifier].append(record_tuple)
        if len(self.records_by_identifiers) == 0:
            print("Bib data file did not contain valid records.", file=sys.stderr)
            sys.exit(1)

    def __contains__(self, item):
        return item in self.records_by_identifiers

    def match(self, new_identifiers):
        matches = set()
        for identifier in new_identifiers:
            if identifier in self.records_by_identifiers:
                matches |= set(self.records_by_identifiers[identifier])
        return matches
