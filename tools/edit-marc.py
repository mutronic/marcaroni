#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:

from pymarc.field import Field
from pymarc import MARCReader
from pymarc import RecordLengthInvalid
import optparse
import os


class OutputHandler:
    def __init__(self, prefix):
        self.prefix = prefix
        self.output_filename = prefix + '-pyedited' + '.mrc'
        print(self.output_filename)
        self.output_fp = open(self.output_filename, 'wb')
        self.count_edited = self.count_missing = 0

    def __del__(self):
        self.output_fp.close()

    def write_marc(self, record):
        self.output_fp.write(record.as_marc())
        self.count_edited += 1


    def write_report(self):
        print("Edited : %d records" % self.count_edited)


def edit_035_for_curio(record):
    url = record['856']['u']
    curio_id = url.rsplit('-',1)[1].replace('/','')
    # Delete existing 035
    record.remove_fields('035')
    # Add new 035
    record.add_ordered_field(
        Field(
            tag = '035',
            indicators = [' ', ' '],
            subfields = [
                'a', '(CA-CURIO){}'.format(curio_id,)
            ]
        )
    )

def edit_035_for_ASP(record):
    asp_id = record['001'].value()
    if '003' in record:
        tcn_source = record['003'].value()
    elif record['040']['a'] == "VaAlASP":
        tcn_source = record['040']['a']
    else:
        tcn_source = record['040']['a']

    # Check if there's an additional one in the 901 - different?
    if '901' in record:
        if record['901']['a'] != asp_id:
            asp_id_2 = record['901']['a']

    string = '({}){}'.format(tcn_source, asp_id)

    # Need new 035?
    f035 = record.get_fields('035')

    # Only add the field if not present.
    for f in f035:
        if f['a'] == string:
            print("already there: " + string)
            return
    record.add_ordered_field(
        Field(
            tag = '035',
            indicators = [' ', ' '],
            subfields = [
                'a', string
            ]
        )
    )

######### Change what gets done by adding or removing functions here. ##########
RULES = [
    #edit_035_for_curio,
    edit_035_for_ASP,
]
################################################################## fin ########


def process(filename):

    output_handler = OutputHandler(prefix=os.path.splitext(filename)[0])
    with open(filename, 'rb') as handler:
        reader = MARCReader(handler, to_unicode=True, force_utf8=True)
        record = reader.__next__()
        while record:
            #print(record['245']['a'])
            for rule in RULES:
                rule(record)
            output_handler.write_marc(record)
            try:
                record = reader.__next__()
            except RecordLengthInvalid:
                record = None

        output_handler.write_report()




def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return args


def main():
    input_files = parse_cmd_line()
    for file in input_files:
        if os.path.exists(file):
            process(file)
        else:
            print("File not found: [%s]" % (file,))


if __name__ == '__main__':
    main()



