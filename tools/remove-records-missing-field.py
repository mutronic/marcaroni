#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

from pymarc.field import Field
from pymarc import MARCReader
import optparse
import os


class OutputHandler:
    def __init__(self, prefix, tag):
        self.prefix = prefix
        self.filtered_filename = prefix + '-containing-' + tag + '.mrc'
        self.filtered_fp = open(self.filtered_filename, 'wb')
        self.missing_filename = prefix + '-missing-' + tag + '.mrc'
        self.missing_fp = open(self.missing_filename, 'wb')
        self.count_filtered = self.count_missing = 0

    def __del__(self):
        self.filtered_fp.close()
        self.missing_fp.close()
        if self.count_missing == 0:
            os.remove(self.filtered_filename)

    def filtered(self, record):
        self.filtered_fp.write(record.as_marc())
        self.count_filtered += 1

    def missing(self, record):
        self.missing_fp.write(record.as_marc())
        self.count_missing += 1

    def write_report(self):
        print("Filtered records containing the tag : %d records" % (self.count_filtered))
        print("Missing the tag   : %d records" % (self.count_missing))


def filter(filename, tag):

    output_handler = OutputHandler(prefix=os.path.splitext(filename)[0], tag=tag)
    with open(filename, 'rb') as handler:
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
        for record in reader:
            #print(record['245']['a'])

            fields = record.get_fields(tag)
            if fields:
                output_handler.filtered(record)
            else:
                output_handler.missing(record)
        output_handler.write_report()


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog --tag=856 INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-t", "--tag", dest="tag", default="856",
                      help="Marc tag used to filter out records missing this tag. Examples are: 856, 598")
    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.tag, args


def main():
    tag, input_files = parse_cmd_line()
    for file in input_files:
        if os.path.exists(file):
            filter(file, tag)
        else:
            print("File not found: [%s]" % (file,))


if __name__ == '__main__':
    main()
