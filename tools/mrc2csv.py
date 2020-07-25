#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

##
# Given a MARC file, export selected fields as csv.

from pymarc.field import Field
from pymarc import MARCReader
import optparse
import os
import csv

class OutputHandler:
    def __init__(self, prefix):
        self.prefix = prefix
        self.output_filename = prefix + '-csv-report.csv'
        self.output_fp = open(self.output_filename, 'w')
        self.output_writer = csv.writer(self.output_fp, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)


    def __del__(self):
        self.output_fp.close()

    def write(self, row):
        self.output_writer.writerow(row)


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    #parser.add_option("-k", "--key", dest="key", default="856",
    #                  help="Key to use to dedupe - available values 856 [def], 001, 245.")
    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return args

def makecsv(file):
    header = ['001', '245', '856', '944', '950']
    output_handler = OutputHandler(prefix=os.path.splitext(file)[0])
    with open(file, 'rb') as handler:
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
        output_handler.write(header)
        for record in reader:
            this_row = []
            for tag in header:
                fields = record.get_fields(tag)
                values = [f.value() for f in fields]
                this_row.append('\t'.join(values))
            output_handler.write(this_row)


def main():
    input_files = parse_cmd_line()
    for file in input_files:
        if os.path.exists(file):
            makecsv(file)
        else:
            print("File not found: [%s]" % (file,))


if __name__ == '__main__':
    main()
