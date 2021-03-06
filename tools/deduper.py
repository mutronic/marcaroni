#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

##
# Given a MARC file,

from pymarc.field import Field
from pymarc import MARCReader
import optparse
import os


class OutputHandler:
    def __init__(self, prefix):
        self.prefix = prefix
        self.deduped_filename = prefix + '-deduped.mrc'
        self.deduped_fp = open(self.deduped_filename, 'wb')
        self.duplicates_filename = prefix + '-dupes.mrc'
        self.dupes_fp = open(self.duplicates_filename, 'wb')
        self.unsure_filename = prefix + '-unsure.mrc'
        self.unsure_fp = open(self.unsure_filename, 'wb')
        self.count_deduped = self.count_unsure = self.count_dupes = 0

    def __del__(self):
        self.deduped_fp.close()
        self.dupes_fp.close()
        self.unsure_fp.close()
        if self.count_dupes == 0:
            os.remove(self.duplicates_filename)
        if self.count_unsure == 0:
            os.remove(self.unsure_filename)

    def deduped(self, record):
        self.deduped_fp.write(record.as_marc())
        self.count_deduped += 1

    def dupe(self, record):
        self.dupes_fp.write(record.as_marc())
        self.count_dupes += 1

    def unsure(self, record):
        self.unsure_fp.write(record.as_marc())
        self.count_unsure += 1

    def write_report(self):
        print("Deduped : %d records" % (self.count_deduped))
        print("Dupes   : %d records" % (self.count_dupes))
        print("Unsure  : %d records" % (self.count_unsure))


def dedupe(filename, key):

    output_handler = OutputHandler(prefix=os.path.splitext(filename)[0])
    registry = set()
    double_header_count = 0
    with open(filename, 'rb') as handler:
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
        for record in reader:
            found_values = [] # All identifier values in this record.
            already_found = [] # List of booleans. Was this identifier previously found?
            id_fields = record.get_fields(key)
            if key == '856':
                for f in id_fields:
                    if f.indicator1 == '4' and f.indicator2 == '0':
                        found_values.append(f['u'])
                        already_found.append(f['u'] in registry)
            if key == '001':
                for f in id_fields:
                        found_values.append(f.value())
                        already_found.append(f.value() in registry)
            if key == '245':
                for f in id_fields:
                        found_values.append(f['a'] + f['b'])
                        already_found.append((f['a'] + f['b']) in registry)

            if all(already_found):
                output_handler.dupe(record)
            elif any(already_found):
                print("Error: can't tell if dupe.")
                output_handler.unsure(record)
                registry |= set(found_values)
            else:
                output_handler.deduped(record)
                registry |= set(found_values)
        output_handler.write_report()


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-k", "--key", dest="key", default="856",
                      help="Key to use to dedupe - available values 856 [def], 001, 245.")
    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.key, args


def main():
    key, input_files = parse_cmd_line()
    for file in input_files:
        if os.path.exists(file):
            dedupe(file, key)
        else:
            print("File not found: [%s]" % (file,))


if __name__ == '__main__':
    main()
