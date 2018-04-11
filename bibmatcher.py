#!/usr/local/bin/python3
#vim: set expandtab:
#vim: tabstop=4:
#vim: ai:
#vim: shiftwidth=4:
from pymarc.field import Field
from pymarc import MARCReader
import sys
import csv
import os
import optparse
from collections import namedtuple

# noinspection PySetFunctionToLiteral
KNOWN_LICENSES = {
    'dda': 0,
    'eba': 1,
    'subscription': 2,
    'purchased': 3,
    'oa': 1,
}


def license_comparator(license_of_match, license_of_input):
    """

    :param license_of_match:
    :param license_of_input:
    :return: True if Match is preferred, False if match is equal or lesser
    """
    if KNOWN_LICENSES[license_of_match] > KNOWN_LICENSES[license_of_input]:
        return True
    else:
        return False


Record = namedtuple('Record', ['id', 'source'])


class UnknownBibSourceLicense(Exception):
    pass


class BibSource:
    def __init__(self, bib_source_id, name, platform, bib_license):
        if bib_license not in KNOWN_LICENSES:
            raise UnknownBibSourceLicense("Bib Source License [%s] is not known" % (bib_license,))
        self.id = bib_source_id
        self.name = name
        self.platform = platform
        self.license = bib_license


class DuplicateBibSource(Exception):
    pass


class BibSourceRegistry:
    def __init__(self):
        self.bib_source_by_id = {}  # dict[str] = BibSource
        self.bib_source_by_platform = {}  # dict[str] = list[BibSource]

    def _add_bib_source(self, bib_source):
        """Add a Bib Source to the registry.

        :type bib_source: BibSource
        """
        if bib_source.id in self.bib_source_by_id:
            raise DuplicateBibSource("Bib Source [%s] is duplicated" % (bib_source.id,))
        self.bib_source_by_id[bib_source.id] = bib_source
        if bib_source.platform not in self.bib_source_by_platform:
            self.bib_source_by_platform[bib_source.platform] = []
        self.bib_source_by_platform[bib_source.platform].append(bib_source)

    def load_from_file(self, filename):
        with open(filename, "r") as in_fp:
            r = csv.DictReader(in_fp)
            for row in r:
                self._add_bib_source(BibSource(bib_source_id=row['id'].strip(),
                                               name=row['name'].strip(),
                                               platform=row['platform'].strip(),
                                               bib_license=row['license'].strip()))

    def get_bib_source_by_id(self, bib_source_id):
        return self.bib_source_by_id[bib_source_id]

    def __contains__(self, item):
        return item in self.bib_source_by_id


def load_bib_data(bib_data_file_name):
    """

    :type bib_data_file_name: str
    :rtype: dict[str, list[Record]]
    """
    # Load the Evergreen Record data as a dict of Records
    # TODO: check the latest update date and prompt to re-load.
    eg_records = {}
    with open(bib_data_file_name, 'r') as datafile:
        myreader = csv.DictReader(datafile, delimiter=',')
        next(myreader)  # skip header
        for row in myreader:
            isbn = row['isbn']
            record_tuple = Record(row['id'], row['source'])
            if isbn not in eg_records:
                eg_records[isbn] = []
            eg_records[isbn].append(record_tuple)
    if len(eg_records) == 0:
        print("ISBN file did not contain valid records.", file=sys.stderr)
        sys.exit(1)
    return eg_records


class OutputRecordHandler:
    def __init__(self, prefix):
        if not os.path.exists(prefix):
          os.makedirs(prefix)
        self.prefix = prefix
        self.add_file_name = os.path.join(prefix, "marc_to_add.mrc")
        self.add_file_fp = open(self.add_file_name, "wb")
        self.update_file_name = os.path.join(prefix, "marc_to_update.mrc")
        self.update_file_fp = open(self.update_file_name, "wb")

        self.ambiguous_file_name = os.path.join(prefix, "marc_ambiguous.mrc")
        self.ambiguous_file_fp = open(self.ambiguous_file_name, "wb")
        self.ambiguous_report_file_name = os.path.join(prefix, "report_ambiguous_records.csv")
        self.ambiguous_report_file_fp = open(self.ambiguous_report_file_name, "w")
        self.ambiguous_report_file_writer = csv.writer(self.ambiguous_report_file_fp)
        self.ambiguous_report_file_writer.writerow(('Title', 'ISBN', 'Reason'))

        self.ignore_file_name = os.path.join(prefix, "marc_to_ignore.mrc")
        self.ignore_file_fp = open(self.ignore_file_name, "wb")
        self.ddas_to_hide_report_file_name = os.path.join(prefix, 'report_existing_dda_records_to_hide.csv')
        self.ddas_to_hide_report_fp = open(self.ddas_to_hide_report_file_name, "w")
        self.ddas_to_hide_report_writer = csv.writer(self.ddas_to_hide_report_fp)
        self.ddas_to_hide_report_writer.writerow(('Title', 'Platform', 'BibId'))

        self.self_ddas_to_hide_report_file_name = os.path.join(prefix, 'report_ddas_from_this_file_to_hide.csv')
        self.self_ddas_to_hide_report_fp = open(self.self_ddas_to_hide_report_file_name, "w")
        self.self_ddas_to_hide_report_writer = csv.writer(self.self_ddas_to_hide_report_fp)
        self.self_ddas_to_hide_report_writer.writerow(('Platform','Title', 'ISBN'))

        self.add_counter = 0
        self.update_counter = 0
        self.ignore_counter = 0
        self.ambiguous_counter = 0

    def __del__(self):
        self.add_file_fp.close()
        self.update_file_fp.close()
        self.ignore_file_fp.close()
        self.ambiguous_file_fp.close()
        self.ddas_to_hide_report_fp.close()

    def add(self, marc_rec):
        self.add_file_fp.write(marc_rec.as_marc())
        self.add_counter += 1

    def ambiguous(self, marc_rec, reason):
        self.ambiguous_file_fp.write(marc_rec.as_marc())
        title = marc_rec['245'].value()
        isbn = marc_rec['020'].value()
        self.ambiguous_report_file_writer.writerow((title, isbn, reason))
        self.ambiguous_counter += 1

    def update(self, marc_rec, bib_id):
        marc_rec.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.update_file_fp.write(marc_rec.as_marc())
        self.update_counter += 1

    def ignore(self, marc_rec):
        self.ignore_file_fp.write(marc_rec.as_marc())
        self.ignore_counter += 1

    def report_of_ddas_to_hide(self, title, platform, bib_id):
        self.ddas_to_hide_report_writer.writerow((title, platform, bib_id))

    def report_of_self_ddas_to_hide(self, platform, title, isbn):
        self.self_ddas_to_hide_report_writer.writerow((platform, title, isbn))

    def print_report(self, bibsources):
        print("Number of records to add:         %d" % (self.add_counter,))
        print("Number of records to update:      %d" % (self.update_counter,))
        print("Number of records to ignore:      %d" % (self.ignore_counter,))
        print("Number of records to figure out:  %d\n" % (self.ambiguous_counter,))
        print("Matches per Bibsource:")
        print("\tsource\tname\t\t\tcount(matches)")
        for source in sorted(bibsource_match_histogram.keys(), reverse=True,
                             key=lambda x: bibsource_match_histogram[x]):
            print("\t%s\t%s: \t%d" % (source, bibsources.get_bib_source_by_id(source).name,
                                      bibsource_match_histogram[source]))


def process_input_files(input_files, bib_source_of_input, bibsources, eg_records):
    output_handler = None
    for filename in input_files:
        if output_handler is None:
            output_handler = OutputRecordHandler(prefix=os.path.splitext(filename)[0])
        with open(filename, 'rb') as handler:
            reader = MARCReader(handler, to_unicode=True, force_utf8=True)
            count = process_input_file(eg_records, reader, output_handler, bib_source_of_input, bibsources)
            print("Record count: " + str(count))
    if output_handler is not None:
        output_handler.print_report(bibsources)


def no_op_filter_predicate(remaining_matches, bib_source_of_inputs, bibsources, marc_record):
    return remaining_matches


FILTER_PREDICATES = [
    no_op_filter_predicate,
]


def filter_matches(matches, bib_source_of_inputs, bibsources, marc_record):
    remaining_matches = set(matches)
    for filter_predicate in FILTER_PREDICATES:
        remaining_matches = filter_predicate(remaining_matches, bib_source_of_inputs, bibsources, marc_record)
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
    title = marc_record['245'].value()
    for m in dda_matches:
        bib_source = bibsources.get_bib_source_by_id(m.source)
        if bib_source.platform == bib_source_of_input.platform:
            continue
        output_handler.report_of_ddas_to_hide(title, bib_source.platform, m.id)

def generate_report_of_self_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record):
    """
    This function will write out a report of all the DDA records on other platforms that
    are rendered moot by the current new record not being a DDA and being for the (nominally)
    same object.
    """
    if bib_source_of_input.license != 'dda':
        return
    non_dda_matches = [m for m in matches if bibsources.get_bib_source_by_id(m.source).license != 'dda']
    if len(non_dda_matches) < 1:
        return
    title = marc_record['245'].value()
    isbn = marc_record['020'].value()
    output_handler.report_of_self_ddas_to_hide(bib_source_of_input.platform, title, isbn)

def handle_special_actions_and_misc_reports(output_handler, matches, bib_source_of_input, bibsources, marc_record):
    generate_report_of_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record)
    generate_report_of_self_ddas_to_hide(output_handler, matches, bib_source_of_input, bibsources, marc_record)


PredicateVector = namedtuple('PredicateVector', ['match_is_dda',
                                                 'match_is_same_platform',
                                                 'match_is_better_license'])


def compute_predicates_for_match(match, match_bib_source, bib_source_of_input, marc_record):
    return PredicateVector(
        match_is_dda=match_bib_source.license == 'dda',
        match_is_same_platform=match_bib_source.platform == bib_source_of_input.platform,
        match_is_better_license=license_comparator(match_bib_source.license, bib_source_of_input.license)
    )


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
            output_handler.ignore(marc_record)
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
        output_handler.update(marc_record, match.id)
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
    output_handler.ambiguous(marc_record, "Record is DDA and all other records too.")
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
    output_handler.add(marc_record)
    return True


def update_same_platform_match_if_unambiguous(marc_record, bib_source_of_input, predicate_vectors,
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
        data = '; '.join(m.id for m in matches_on_this_platform)
        output_handler.ambiguous(marc_record, "There are multiple matches on this platform. " + data)
        return True
    if predicate_vectors[matches_on_this_platform[0]].match_is_better_license:
        output_handler.ignore(marc_record)
        return True
    output_handler.update(marc_record, matches_on_this_platform[0].id)
    return True


RULES = [
    ignore_if_new_record_is_dda_and_better_is_available,
    update_same_dda_record_if_unambiguous,
    mark_as_ambiguous_new_record_is_dda_and_better_is_not_available,
    add_if_all_matches_are_on_other_platforms,
    update_same_platform_match_if_unambiguous,
]


def process_input_file(eg_records, reader, output_handler, bib_source_of_input, bibsources):
    """

    :type eg_records: dict[str, list[Record]]
    :type reader: MARCReader
    :type output_handler: OutputRecordHandler
    :type bib_source_of_input: BibSource
    :type bibsources: BibSourceRegistry
    :return: int
    """
    count = 0
    for marc_record in reader:
        count += 1
        matches = match_marc_record_against_bib_data(eg_records, marc_record)
        if len(matches) == 0:
            output_handler.add(marc_record)
        else:
            remaining_matches, removed_matches = filter_matches(matches, bib_source_of_input, bibsources, marc_record)
            handle_special_actions_and_misc_reports(output_handler, remaining_matches, bib_source_of_input,
                                                    bibsources, marc_record)
            # Now we need to know things about the remaining matches so we may make decision on them.
            predicate_vectors = {}
            for match in remaining_matches:
                predicate_vectors[match] = compute_predicates_for_match(match,
                                                                        bibsources.get_bib_source_by_id(match.source),
                                                                        bib_source_of_input,
                                                                        marc_record)

            done = False
            for rule in RULES:
                if rule(marc_record, bib_source_of_input, predicate_vectors, output_handler):
                    done = True
                    break

            if not done:
                output_handler.ambiguous(marc_record, "One of more match but no rules matched.")

    return count


bibsource_match_histogram = {}


def match_marc_record_against_bib_data(eg_records, record):
    # Set up a place to put matching record things.
    matches = set()
    # Get all ISBNs
    for f in record.get_fields('020'):
        for subfield in ['a', 'z']:
            if f[subfield]:
                cleaned = f[subfield].strip()
                new_isbn = cleaned.split(' ')[0]
                # We did less cleaning on the incoming ISBNS: this is our chance to fix them!!
                if len(new_isbn) not in [10, 13]:
                    print('Probably a bad isbn: ' + new_isbn)
                if new_isbn in eg_records:
                    matches |= set(eg_records[new_isbn])

    for match in matches:
        if match.source not in bibsource_match_histogram:
            bibsource_match_histogram[match.source] = 0
        bibsource_match_histogram[match.source] += 1
    return matches


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-b", "--bib-data", dest="bib_data", default="bib-data.txt",
                      help="CSV file of Bib Data to use")
    parser.add_option("-s", "--bib-source", dest="bib_source", default="bib_sources.csv",
                      help="CSV file of Bib Sources to use")
    opts, args = parser.parse_args()

    if not os.path.exists(opts.bib_data):
        parser.error("Bib data file [%s] not found." % (opts.bib_data,))
    if not os.path.exists(opts.bib_source):
        parser.error("Bib source file [%s] not found." % (opts.bib_source,))

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.bib_source, opts.bib_data, args


def main():
    bib_source_file_name, bib_data_file_name, input_files = parse_cmd_line()

    # CONFIG:
    bibsources = BibSourceRegistry()
    bibsources.load_from_file(bib_source_file_name)
    bibsource = input("Please enter the number of the bibsource:").strip()

    if bibsource not in bibsources:
        print("Bib source [%s] is not known to Marc-a-roni." % (bibsource,), file=sys.stderr)
        sys.exit(2)
    print("\nYou have chosen the [%s] Bib Source\n" % (bibsources.get_bib_source_by_id(bibsource).name,))

    eg_records = load_bib_data(bib_data_file_name)

    process_input_files(input_files, bibsources.get_bib_source_by_id(bibsource), bibsources, eg_records)


if __name__ == '__main__':
    main()
