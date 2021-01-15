#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

##
# Given a MARC file, extract the first N records to a new file.

from pymarc.field import Field
from pymarc import MARCReader
import optparse
import os


class OutputHandler:
    def __init__(self, prefix):
        self.prefix = prefix
        self.output_filename = prefix + '-head.mrc'
        self.output_fp = open(self.output_filename, 'wb')

    def __del__(self):
        self.output_fp.close()

    def output(self, record):
        self.output_fp.write(record.as_marc())

def head(filename, max_count):
    output_handler = OutputHandler(prefix=os.path.splitext(filename)[0])
    with open(filename, 'rb') as handler:
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
        count = 0
        for record in reader:
            output_handler.output(record)
            count += 1
            if count < max_count:
                continue
            break

def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-n", "--count", dest="count", default="5",
                      help="Number of marc records to output from the beginning of the marc file.")
    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return int(opts.count), args


def main():
    count, input_files = parse_cmd_line()
    for file in input_files:
        if os.path.exists(file):
            head(file, count)
        else:
            print("File not found: [%s]" % (file,))


if __name__ == '__main__':
    main()
