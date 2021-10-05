#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:
import sys
import csv
import os
import optparse
from collections import namedtuple
from collections import Counter
import datetime
import re

from pymarc.field import Field
from pymarc import MARCReader
import isbnlib

import marcaroni.ils
import marcaroni.sources
import marcaroni.output


def no_op_filter_function(remaining_matches, bib_source_of_inputs, bibsources, marc_record):
    return remaining_matches


FILTER_FUNCTIONS = [
    no_op_filter_function,
]


def filter_matches(matches, bib_source_of_inputs, bibsources, marc_record):
    """
    This doesn't do anything yet, but could be used to remove undesired matches.
    :param matches:
    :param bib_source_of_inputs:
    :param bibsources:
    :param marc_record:
    :return:
    """
    remaining_matches = set(matches)
    for filter_function in FILTER_FUNCTIONS:
        remaining_matches = filter_function(remaining_matches, bib_source_of_inputs, bibsources, marc_record)
    return remaining_matches, matches - remaining_matches


def generate_report_of_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record):
    """
    This function will write out a report of all the DDA records on other platforms that
    are rendered moot by the current new record not being a DDA and being for the (nominally)
    same object.
    """
    if bib_source_of_input.license == 'dda':
        return
    dda_matches = [m for m in matches if bibsources.get_bib_source_by_id(m.source).license == 'dda']
    if len(dda_matches) < 1:
        return
    for m in dda_matches:
        bib_source = bibsources.get_bib_source_by_id(m.source)
        if bib_source.platform == bib_source_of_input.platform:
            continue
        output_handler.report_of_ddas_to_hide(bib_source.platform, marc_record.title, m.id)

def generate_report_of_self_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record):
    """
    This function will write out a report of all the records in this batch that we should NOT load
    because we have another copy in a better profile.
    """
    if bib_source_of_input.license != 'dda':
        return
    non_dda_matches = [m for m in matches if bibsources.get_bib_source_by_id(m.source).license != 'dda']
    if len(non_dda_matches) < 1:
        return
    url = marc_record.marc['856']['u']
    output_handler.report_of_self_ddas_to_hide(bib_source_of_input.platform, marc_record.title, url)

def handle_special_actions_and_misc_reports(output_handler, matches, bib_source_of_input, bibsources, marc_record):
    generate_report_of_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record)
    generate_report_of_self_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record)



PredicateVector = namedtuple('PredicateVector', ['match_is_dda',
                                                 'match_is_same_platform',
                                                 'match_is_better_license',
                                                 'match_is_odd_bibsource'])


def license_comparator(license_of_existing, license_of_input):
    """
    This function tells you if the incoming (input) license is better than the existing.
    If so, we probably want to update the existing record to reflect the better license.
    In particular, this affects records for purchased items - the perpetual access means
    that the record should be "upgraded" if it were DDA or subscription.

    :param license_of_existing:
    :param license_of_input:
    :return: True if Match is preferred, False if match is equal or lesser
    """
    if marcaroni.sources.KNOWN_LICENSES[license_of_existing] > marcaroni.sources.KNOWN_LICENSES[license_of_input]:
        return True
    else:
        return False


def compute_predicates_for_match(match, match_bib_source, bib_source_of_input, marc_record):
    return PredicateVector(
        match_is_dda=match_bib_source.license == 'dda',
        match_is_same_platform=match_bib_source.platform == bib_source_of_input.platform,
        match_is_better_license=license_comparator(match_bib_source.license, bib_source_of_input.license),
        match_is_odd_bibsource=(match_bib_source.id in ['81', '59', '56', '43', '22', '21', '9', '6'])
    )

def ambiguous_if_matches_on_ambiguous_bibsource(marc_record, bib_source_of_input, predicate_vectors, output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: Dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    n = len(predicate_vectors)
    for matching_record in list(predicate_vectors.keys()):
        if matching_record.source in ['81', '59', '56', '43', '22', '21', '9', '6']:
            output_handler.ambiguous(marc_record, "Record matched " + str(n) + " record(s), including at least one "
                                                                          "ambiguous bibsource. record: " +
                                     matching_record.id + " source: " + matching_record.source)
            return True
    return False



def ignore_if_new_record_is_dda_and_better_is_available(marc_record, bib_source_of_input, predicate_vectors,
                                                        output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: Dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    if bib_source_of_input.license != 'dda':
        return False
    for match in predicate_vectors:
        if predicate_vectors[match].match_is_better_license:
            output_handler.match_is_better(marc_record)
            return True
    return False

def ignore_depending_on_publisher(marc_record, bib_source_of_input, predicate_vectors,
                                                        output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: Dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    if bib_source_of_input.id != '1':
        return False
    pub_tags = ['264', '260']
    for tag in pub_tags:
      for f in marc_record.get_fields(tag):
        if f['b'] & f['b'].startswith('Nova Science'):
            output_handler.match_is_better(marc_record)
            return True
    return False


def update_same_dda_record_if_unambiguous(marc_record, bib_source_of_input, predicate_vectors, output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    if bib_source_of_input.license != 'dda':
        return False
    if len(predicate_vectors) != 1:
        return False
    match = list(predicate_vectors.keys())[0]
    if not predicate_vectors[match].match_is_same_platform:
        return False
    if predicate_vectors[match].match_is_dda:
        output_handler.exact_match(marc_record, match.id)
        return True
    return False


def mark_as_ambiguous_new_record_is_dda_and_better_is_not_available(marc_record, bib_source_of_input, predicate_vectors,
                                                                    output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    if bib_source_of_input.license != 'dda':
        return False
    for match in predicate_vectors:
        if predicate_vectors[match].match_is_better_license:
            return False
    data = '; '.join(m.id for m in predicate_vectors.keys())
    output_handler.ambiguous(marc_record, "Record is DDA and all other records too. Consult fall-through. " + data)
    return True


def add_if_all_matches_are_on_other_platforms(marc_record, bib_source_of_input, predicate_vectors,
                                              output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    for match in predicate_vectors:
        if predicate_vectors[match].match_is_same_platform:
            return False
    output_handler.no_match(marc_record)
    return True


def handle_same_platform_matches(marc_record, bib_source_of_input, predicate_vectors,
                                 output_handler):
    """

    :param marc_record:
    :param bib_source_of_input: BibSource
    :type predicate_vectors: dict[Record, PredicateVector]
    :type output_handler: OutputRecordHandler
    :rtype: bool
    """
    matches_on_this_platform = []
    for match in predicate_vectors:
        if predicate_vectors[match].match_is_same_platform:
            matches_on_this_platform.append(match)
    if len(matches_on_this_platform) <= 0:
        return False
    if len(matches_on_this_platform) > 1:
        data = [m.id + ' (' + m.source + ')' for m in matches_on_this_platform]
        data.sort()
        info = ' ; '.join(data)
        output_handler.ambiguous(marc_record, "There are multiple matches on this platform. " + info)
        return True
    single_match = matches_on_this_platform[0]
    if single_match.source == bib_source_of_input.id:
        output_handler.exact_match(marc_record, single_match.id)
        return True
    if predicate_vectors[single_match].match_is_better_license:
        output_handler.match_is_better(marc_record)
        return True
    output_handler.match_is_worse(marc_record, single_match.id)
    return True


RULES = [
    #ambiguous_if_matches_on_ambiguous_bibsource,
    ignore_depending_on_publisher,
    ignore_if_new_record_is_dda_and_better_is_available,
    update_same_dda_record_if_unambiguous,
    mark_as_ambiguous_new_record_is_dda_and_better_is_not_available,
    add_if_all_matches_are_on_other_platforms,
    handle_same_platform_matches,
]


def process_input_files(input_files, bib_source_of_input, bibsources, eg_records, match_field):
    output_handler = None
    bibsource_prefix = re.sub('[^A-Za-z0-9]','_',bib_source_of_input.name)
    for filename in input_files:
        f, ext = os.path.splitext(filename)
        if ext != '.mrc':
            print("This is not a marc file: " + filename)
            exit(1)
        if output_handler is None:
            output_handler = marcaroni.output.OutputRecordHandler(prefix=os.path.splitext(filename)[0], bibsource_prefix=bibsource_prefix)
        with open(filename, 'rb') as handler:
            if output_handler is not None:
                output_handler.logger("Bibsource: %s"%(bib_source_of_input.name))
            reader = MARCReader(handler, to_unicode=True, force_utf8=True)
            total_record_count = process_mrc_file(eg_records, reader, output_handler, bib_source_of_input, bibsources, match_field)
            if output_handler is not None:
                output_handler.print_report(bibsources, total_record_count)

def extract_identifiers_from_row(row, isbn_columns):
    cols = [int(x) for x in isbn_columns.split(',')]
    isbns = set()
    for isbn_column in cols:
        raw = row[isbn_column].strip('"=')
        isbns.add(raw)
        # Transform to ISBN 10 or 13.
        if isbnlib.is_isbn13(raw):
            isbns.add(isbnlib.to_isbn10(raw))
        elif isbnlib.is_isbn10(raw):
            isbns.add(isbnlib.to_isbn13(raw))
    return isbns


def match_input_files(input_files, bibsources, eg_records, isbn_columns, negate):
    '''
    This function is for the Excel matching. Spreadsheet must have a header row.

    :param input_files:
    :param bibsources: BibSourceRegistry
    :param eg_records: ILSBibData
    :param isbn_columns: str
    :param negate:
    :return:
    '''

    other_sources_on_platform = bibsources.other_sources_on_platform()

    for filename in input_files:
        prefix = os.path.splitext(filename)[0]

        # Avoiding output handler. Just throw -matched.csv on there. FIXME - use different handler?
        outfile = open(prefix + '-matched.csv', 'w')
        out_writer = csv.writer(outfile)

        with open(filename, 'r') as handler:
            reader = csv.reader(handler)

            # If on first try you get a single column, try again with tab delimiter.
            first_row = next(reader)
            if len(first_row) < 2:
                reader = csv.reader(handler, delimiter='\t')
                first_row = next(reader)

            # OUTPUT - requires first line.
            # Add our custom output columns, and write first row of output spreadsheet.
            # Columns are: Same bibsource, Same platform, Other platforms
            first_row[0:0] = ['Same bibsource', 'Same platform', 'Other platforms']
            out_writer.writerow(first_row)

            histogram = Counter()

            for row in reader:
                matches = set()

                isbns = extract_identifiers_from_row(row, isbn_columns)
                matches = eg_records.match(isbns)

                # Add to histogram.
                for x in matches:
                    histogram[x.source] += 1

                # sort matches.
                matches_with_same_bibsource = []
                matches_with_same_platform = []
                matches_with_different_platform = []
                for match in matches:
                    if match.source == bibsources.selected.id:
                        matches_with_same_bibsource.append(match)
                    elif match.source in other_sources_on_platform:
                        matches_with_same_platform.append(match)
                    else:
                        matches_with_different_platform.append(match)

                # Create printable strings.
                row.insert(0, [csvify(matches_with_same_bibsource),
                               csvify(matches_with_same_platform),
                               csvify(matches_with_different_platform)
                               ])
                out_writer.writerow(row)


        outfile.close()

        print("\nMatches per Bibsource:")
        print("\tsource\tcount(records)")
        for source in sorted(histogram.keys(), reverse=True,
                             key=lambda x: histogram[x]):
            print("\t%s: \t%d" % (source, histogram[source]))

def csvify(match_list):
    if len(match_list) == 0:
        return "NULL"
    elif len(match_list) == 1:
        return match_list[0].id
    else:
        return "multi: " + ','.join([x.id for x in match_list])

class PendingRecord:
    def __init__(self, marc_record, bibsource, id_field, sequence):
        self.marc = marc_record
        self.source = bibsource
        self.id_field = id_field
        self.sequence = sequence
        self._extract_identifiers()
        self.title = 'No title'
        if self.marc['245']:
            self.title = self.marc['245'].value()
        self.isbn = 'No isbn'
        if self.marc['020']:
            self.isbn = self.marc['020'].value()

    def as_marc(self):
        return self.marc.as_marc()

    def ldr_to_utf8(self):
        self.marc.leader = self.marc.leader[0:9] + 'a' + self.marc.leader[10:]
        pass

    def verify_856(self):
        if not self.marc['856']:
            return False
        else:
            return True

    def _extract_identifiers(self):
        self.identifiers = set()
        # Loop over all fields and 'a','z' subfields.
        for f in self.marc.get_fields(self.id_field):
            for subfield in ['a', 'z']:
                for value in f.get_subfields(subfield):
                    if self.id_field == '020':
                        cleaned = value.strip()
                        cleaned = cleaned.split('(')[0]
                        incoming_identifier = cleaned.split(' ')[0]
                        # We did less cleaning on the incoming ISBNS: this is our chance to fix them!!
                        if len(incoming_identifier) not in [10, 13]:
                            print('Probably a bad isbn: ' + incoming_identifier)
                    elif self.id_field == '035':
                        cleaned = value.replace('(',' ')
                        cleaned = cleaned.replace(')',' ')
                        cleaned = cleaned.replace('-',' ')
                        cleaned = cleaned.lower()
                        incoming_identifier = cleaned.strip()
                    # A valid identifier contains numbers.
                    elif self.id_field == '856':
                        cleaned = re.sub(value, r'.*url=', '')
                        cleaned = cleaned.replace(':',' ')
                        cleaned = cleaned.replace('/',' ')
                        cleaned = cleaned.replace('\.',' ')
                        cleaned = cleaned.replace('/',' ')
                        incoming_identifier = cleaned.strip()
                    if any(i.isdigit() for i in incoming_identifier) and len(incoming_identifier) > 7:
                        self.identifiers.add(incoming_identifier)
        if len(self.identifiers) == 0:
            return False
        return self.identifiers


def process_mrc_file(eg_records, reader, output_handler, bib_source_of_input, bibsources, match_field):
    """

    :type eg_records: marcaroni.ils.ILSBibData
    :type reader: MARCReader
    :type output_handler: OutputRecordHandler
    :type bib_source_of_input: BibSource
    :type bibsources: BibSourceRegistry
    :type match_field: str
    :return: int
    """
    records_processed_count = 0
    for marc_record in reader:
        records_processed_count += 1

        record = PendingRecord(marc_record, bibsources.selected, match_field, records_processed_count)
        record.ldr_to_utf8()

        # Convert record encoding to UTF-8 in leader.
        marc_record.leader = marc_record.leader[0:9] + 'a' + marc_record.leader[10:]

        # Ensure record has title. Warn if not.
        if record.title == '<>.':
            print("WARNING: <>. as a title found! at record no {}".format( str(records_processed_count)), file=sys.stderr)

        # Ensure record has 856. Exit if not.
        if not record.verify_856():
            print("ERROR: NO 856 IN RECORD #[{}], Title: [{}]".format(str(records_processed_count),record.title), file=sys.stderr)
            sys.exit(1)

        # Ensure record has identifier. Ambiguous if not.
        if len(record.identifiers) < 1:
            print("WARNING: NO {} identifier! at record no {}, Title: [{}]".format(match_field, str(records_processed_count), record.title), file=sys.stderr)
            output_handler.ambiguous(record, "Record has no identifier in {}.".format(match_field,))
            continue

        # Calculate Matches
        matches = eg_records.match(record.identifiers)
        output_handler.count_matches_by_bibsource(matches)

        if len(matches) == 0:
            output_handler.no_match(record)
            continue
        else:
            remaining_matches, removed_matches = filter_matches(matches, bib_source_of_input, bibsources, record)
            handle_special_actions_and_misc_reports(output_handler, remaining_matches, bib_source_of_input,
                                                    bibsources, record)
            # Now we need to know things about the remaining matches so we may make decision on them.
            predicate_vectors = {}
            for match in remaining_matches:
                predicate_vectors[match] = compute_predicates_for_match(match,
                                                                        bibsources.get_bib_source_by_id(match.source),
                                                                        bib_source_of_input,
                                                                        marc_record)

            done = False
            for rule in RULES:
                if rule(record, bib_source_of_input, predicate_vectors, output_handler):
                    done = True
                    break

            if not done:
                output_handler.ambiguous(record, "One or more match but no rules matched.")

    return records_processed_count


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog [options] INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-d", "--bib-data", dest="bib_data", default="bib-data.txt",
                      help="CSV file of Bib Data to use. [default: %default]")
    parser.add_option("--bib-source-file", dest="bib_source_file", default=os.path.join(os.path.dirname(__file__), 'conf', 'bib_sources.csv'),
                      help="CSV file of Bib Sources to use. [default: %default]")
    parser.add_option("-s", "--bib-source", dest="bib_source",
                      help="Numerical id of bib source for this batch. If empty, will prompt for this.")
    parser.add_option("-x", "--excel", action="store_true", dest="excel", default=False,
                      help="Instead of a .mrc file, the input is a CSV file. Output will be a modified CSV file..")
    parser.add_option("-n", "--negate", action="store_true", dest="negate", default=False,
                      help="For an excel report, find matches NOT in a specific bibsource.")
    parser.add_option("-m", "--match-field", dest="match_field", default='',
                      help="Marc tag to use as identifier. Options are '020' or '035'. Default depends on bibsource.")
    opts, args = parser.parse_args()

    if not os.path.exists(opts.bib_data):
        parser.error("Bib data file [%s] not found." % (opts.bib_data,))
    if not os.path.exists(opts.bib_source_file):
        parser.error("Bib source file [%s] not found." % (opts.bib_source,))

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.bib_source_file, opts.bib_source, opts.bib_data, opts.excel, opts.negate, opts.match_field, args


def prompt_for_bib_source(bibsources):
    """

    :param bibsources: BibSourceRegistry
    :return:
    """
    response = input("Please enter the number of the bibsource. Or, enter the first few letters to look one up: ").strip()
    while response not in bibsources:
        suggestions = bibsources.autosuggest(response)
        for s in suggestions:
            print("{: <40}\t{}".format(s[0], s[1]))
        response = input("Please enter the number of the bibsource. Or, enter the first few letters to look one up: ").strip()
    return response


def main():
    bib_source_file_name, bib_source_id, bib_data_file_name, excel, negate, match_field, input_files = parse_cmd_line()

    bibsources = marcaroni.sources.BibSourceRegistry()
    bibsources.load_from_file(bib_source_file_name)

    if not bib_source_id:
        bib_source_id = prompt_for_bib_source(bibsources)
    bibsources.set_selected(bib_source_id)
    print("\nYou have chosen the [%s] Bib Source." % (bibsources.selected.name,))

    if not match_field:
        match_field = bibsources.get_match_field()
        print("This bibsource matches on field: %s.\n" % (match_field))
    else:
        print("Matching on field: %s.\n" % (match_field))

    print("Loading records from %s" % (bib_data_file_name))
    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(bib_data_file_name))
    print("File last modified: %s" % (mod_time))
    if mod_time < (datetime.datetime.now() - datetime.timedelta(hours=1)):
        input("WARNING! Bib data is old. Press a key to continue, or Ctrl-D to cancel ")

    eg_records = marcaroni.ils.ILSBibData()
    eg_records.load_from_file(bib_data_file_name, match_field)

    if excel:
        isbn_columns = input("Identifier (e.g. ISBN) column(s) separated by commas, counting from 0: ")
        match_input_files(input_files, bibsources, eg_records, isbn_columns, negate)
        return
    print("Processing input files.")
    process_input_files(input_files, bibsources.selected, bibsources, eg_records, match_field)


if __name__ == '__main__':
    main()
