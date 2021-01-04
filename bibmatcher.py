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
import re
import logging
import isbnlib
import datetime

# noinspection PySetFunctionToLiteral
KNOWN_LICENSES = {
    'dda': 0,
    'eba': 1,
    'subscription': 2,
    'purchased': 3,
    'oa': 1,
}

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
    if KNOWN_LICENSES[license_of_existing] > KNOWN_LICENSES[license_of_input]:
        return True
    else:
        return False

# Rename this? KnownRecord? ExistingRecord?
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


def load_bib_data(bib_data_file_name, match_field = '020'):
    """

    :type bib_data_file_name: str
    :type match_field: str
    :rtype: dict[str, list[Record]]
    """
    # Load the Evergreen Record data. Makes a dictionary keyed by  identifier (i.e. isbn or 035 string).
    # Each value in the dictionary is a list of Records.
    eg_records = {}
    with open(bib_data_file_name, 'r') as datafile:
        myreader = csv.DictReader(datafile, delimiter=',')
        next(myreader)  # skip header, which is 'identifier,id,source,tag,subfield'
        for row in myreader:
            if row['tag'] != match_field:
                continue
            identifier = row['identifier']
            record_tuple = Record(row['id'], row['source'])
            if identifier not in eg_records:
                eg_records[identifier] = []
            eg_records[identifier].append(record_tuple)
    if len(eg_records) == 0:
        print("Bib data file did not contain valid records.", file=sys.stderr)
        sys.exit(1)
    return eg_records


class OutputRecordHandler:
    def __init__(self, prefix, bibsource_prefix):
        if not os.path.exists(prefix):
          os.makedirs(prefix)
        self.prefix = prefix

        # Initialize logging
        log_level = logging.INFO
        log_format = '  %(message)s'
        handlers = [logging.FileHandler(os.path.join(prefix, 'marcaroni.log')), logging.StreamHandler()]
        logging.basicConfig(level = log_level, format = log_format, handlers = handlers)
        logging.info("\nStarting Marcaroni: %s" %(datetime.datetime.now(), ) )

        # Output file for incoming records with no match found.
        self.no_matches_on_platform__file_name = os.path.join(prefix, bibsource_prefix + "_no_matches_on_platform.mrc")
        self.no_matches_on_platform__file_pointer = open(self.no_matches_on_platform__file_name, "wb")
        self.records_without_matches_counter = 0

        # Output file for incoming records with one match on the platform, having a worse license.
        self.match_has_worse_license__file_name = os.path.join(prefix, bibsource_prefix + "_match_has_worse_license.mrc")
        self.match_has_worse_license__file_pointer = open(self.match_has_worse_license__file_name, "wb")
        self.match_has_worse_license__counter = 0

        # Output file for incoming records with one match on the platform, having the same bibsource.
        self.exact_match__file_name = os.path.join(prefix, bibsource_prefix + "_exact_match_same_bibsource.mrc")
        self.exact_match__file_pointer = open(self.exact_match__file_name, "wb")
        self.exact_match__counter = 0

        # Output file for incoming records with one match on the platform, having a better license.
        self.match_has_better_license__file_name = os.path.join(prefix, bibsource_prefix + "_match_has_better_license.mrc")
        self.match_has_better_license__file_pointer = open(self.match_has_better_license__file_name, "wb")
        self.match_has_better_license__counter = 0

        # Output file for incoming records with multiple matches on the same platform (or are otherwise ambiguous).
        self.ambiguous__file_name = os.path.join(prefix, bibsource_prefix + "_ambiguous.mrc")
        self.ambiguous__file_pointer = open(self.ambiguous__file_name, "wb")
        self.ambiguous_report__file_name = os.path.join(prefix, "report_ambiguous_records.csv")
        self.ambiguous_report__file_pointer = open(self.ambiguous_report__file_name, "w")
        self.ambiguous_report__csv_writer = csv.writer(self.ambiguous_report__file_pointer)
        self.ambiguous_report__csv_writer.writerow(('Title', 'ISBN', 'Reason'))
        self.ambiguous__counter = 0

        # Remove these - build a reporting script at some other point. Unlikely to match on record ID (035) across
        # distributor platforms.
        self.ddas_to_hide_report_file_name = os.path.join(prefix, 'report_existing_dda_records_to_hide.csv')
        self.ddas_to_hide_report_fp = open(self.ddas_to_hide_report_file_name, "w")
        self.ddas_to_hide_report_writer = csv.writer(self.ddas_to_hide_report_fp, dialect='excel-tab')
        # self.ddas_to_hide_report_writer.writerow(('Platform', 'Title', 'BibId'))
        self.old_ddas_counter = 0

        self.self_ddas_to_hide_report_file_name = os.path.join(prefix, 'report_ddas_from_this_file_to_hide.csv')
        self.self_ddas_to_hide_report_fp = open(self.self_ddas_to_hide_report_file_name, "w")
        self.self_ddas_to_hide_report_writer = csv.writer(self.self_ddas_to_hide_report_fp, dialect='excel-tab')
        # self.self_ddas_to_hide_report_writer.writerow(('Platform','Title', 'BibId', '856'))
        self.self_ddas_counter = 0


    def __del__(self):
        self.no_matches_on_platform__file_pointer.close()
        self.match_has_worse_license__file_pointer.close()
        self.exact_match__file_pointer.close()
        self.match_has_better_license__file_pointer.close()
        self.ambiguous__file_pointer.close()

        # Deprecated - I hope.
        self.ddas_to_hide_report_fp.close()
        self.self_ddas_to_hide_report_fp.close()

        # Delete files that weren't used.
        if self.records_without_matches_counter == 0:
            os.remove(self.no_matches_on_platform__file_name)
        if self.match_has_worse_license__counter == 0:
            os.remove(self.match_has_worse_license__file_name)
        if self.exact_match__counter == 0:
            os.remove(self.exact_match__file_name)
        if self.match_has_better_license__counter == 0:
            os.remove(self.match_has_better_license__file_name)
        if self.ambiguous__counter == 0:
            os.remove(self.ambiguous__file_name)
            os.remove(self.ambiguous_report__file_name)
        if self.old_ddas_counter == 0:
            os.remove(self.ddas_to_hide_report_file_name)
        if self.self_ddas_counter == 0:
            os.remove(self.self_ddas_to_hide_report_file_name)

    def no_match(self, marc_rec):
        self.no_matches_on_platform__file_pointer.write(marc_rec.as_marc())
        self.records_without_matches_counter += 1

    def match_is_worse(self, marc_rec, bib_id):
        marc_rec.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.match_has_worse_license__file_pointer.write(marc_rec.as_marc())
        self.match_has_worse_license__counter += 1

    def exact_match(self, marc_rec, bib_id):
        marc_rec.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.exact_match__file_pointer.write(marc_rec.as_marc())
        self.exact_match__counter += 1

    def match_is_better(self, marc_rec):
        self.match_has_better_license__file_pointer.write(marc_rec.as_marc())
        self.match_has_better_license__counter += 1

    def ambiguous(self, marc_rec, reason):
        self.ambiguous__file_pointer.write(marc_rec.as_marc())
        title = marc_rec['245'].value()
        isbn = marc_rec['020']
        if isbn:
            isbn = isbn.value()
        else:
            isbn = 'no isbn'
        self.ambiguous_report__csv_writer.writerow((title, isbn, reason))
        self.ambiguous__counter += 1

    def report_of_ddas_to_hide(self, platform, title, bib_id):
        self.ddas_to_hide_report_writer.writerow((platform, title, bib_id))
        self.old_ddas_counter += 1

    def report_of_self_ddas_to_hide(self, platform, title, isbn):
        self.self_ddas_to_hide_report_writer.writerow((platform, title, '', isbn))
        self.self_ddas_counter += 1

    def print_report(self, bibsources, total_record_count):
        logging.info("Record count: " + str(total_record_count))
        logging.info("# not found on this platform:          %d" % (self.records_without_matches_counter,))
        logging.info("# found same platform, worse license:  %d" % (self.match_has_worse_license__counter,))
        logging.info("# found same platform, same license:   %d" % (self.exact_match__counter,))
        logging.info("# found same platform, better license: %d" % (self.match_has_better_license__counter,))
        logging.info("# ambiguous:                           %d" % (self.ambiguous__counter,))
        if (self.old_ddas_counter > 0):
            logging.info("DDAs that need to be deleted: \t%d" % (self.old_ddas_counter))

        if (self.self_ddas_counter > 0):
            logging.info("DDAs from this batch that need to be deactivated: %d" % (self.self_ddas_counter))

        logging.info("\nMatches By Bibsource:")
        logging.info("\tsource\tname\tcount(records)")
        for source in sorted(bibsource_match_histogram.keys(), reverse=True,
                             key=lambda x: bibsource_match_histogram[x]):
            logging.info("\t%s\t%s: \t%d" % (source, bibsources.get_bib_source_by_id(source).name,
                                      bibsource_match_histogram[source]))

    def logger(self, message):
        logging.info(message)


def process_input_files(input_files, bib_source_of_input, bibsources, eg_records, match_field):
    output_handler = None
    bibsource_prefix = re.sub('[^A-Za-z0-9]','_',bib_source_of_input.name)
    for filename in input_files:
        if output_handler is None:
            output_handler = OutputRecordHandler(prefix=os.path.splitext(filename)[0], bibsource_prefix=bibsource_prefix)
        with open(filename, 'rb') as handler:
            if output_handler is not None:
                output_handler.logger("Bibsource: %s"%(bib_source_of_input.name))
            reader = MARCReader(handler, to_unicode=True, force_utf8=True)
            total_record_count = process_input_file(eg_records, reader, output_handler, bib_source_of_input, bibsources, match_field)
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


def determine_other_sources_on_platform(selected_bib_source, all_bib_sources):
    related_source_ids = set()
    sources_on_platform = all_bib_sources.bib_source_by_platform[selected_bib_source.platform]
    for source in sources_on_platform:
        if source.id != selected_bib_source.id:
            related_source_ids.add(source.id)
    return related_source_ids

def match_input_files(input_files, bib_source_of_input, bibsources, eg_records, isbn_columns, negate):
    '''
    This function is for the Excel matching. Spreadsheet must have a header row.

    :param input_files:
    :param bib_source_of_input:
    :param bibsources: BibSourceRegistry
    :param eg_records:
    :param isbn_columns: str
    :param negate:
    :return:
    '''

    other_sources_on_platform = determine_other_sources_on_platform(bib_source_of_input, bibsources)

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

            bibsource_match_histogram = {}

            for row in reader:
                matches = set()

                isbns = extract_identifiers_from_row(row, isbn_columns)
                for isbn in isbns:
                    if isbn in eg_records:
                        matches |= set(eg_records[isbn]) # Union of sets.

                # Add to histogram.
                for x in matches:
                    if x.source not in bibsource_match_histogram:
                        bibsource_match_histogram[x.source] = 0
                    bibsource_match_histogram[x.source] += 1

                # sort matches.
                matches_with_same_bibsource = []
                matches_with_same_platform = []
                matches_with_different_platform = []
                for match in matches:
                    if match.source == bib_source_of_input.id:
                        matches_with_same_bibsource.append(match)
                    elif match.source in other_sources_on_platform:
                        matches_with_same_platform.append(match)
                    else:
                        matches_with_different_platform.append(match)

                # Create printable strings.


                if len(matches_with_same_bibsource) == 0:
                    row.insert(0, "NULL")
                    out_writer.writerow(row)
                elif len(matches_with_same_bibsource) == 1:
                    row.insert(0, matches_with_same_bibsource[0].id)
                    out_writer.writerow(row)
                else:
                    note = "multi: " + ','.join([x.id for x in matches_with_same_bibsource])
                    print(row)
                    row.insert(0, note)
                    out_writer.writerow(row)

        outfile.close()

        print("\nMatches per Bibsource:")
        print("\tsource\tcount(records)")
        for source in sorted(bibsource_match_histogram.keys(), reverse=True,
                             key=lambda x: bibsource_match_histogram[x]):
            print("\t%s: \t%d" % (source, bibsource_match_histogram[source]))


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
    for filter_predicate in FILTER_FUNCTIONS:
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
        output_handler.report_of_ddas_to_hide(bib_source.platform, title, m.id)

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
    title = marc_record['245'].value()
    url = marc_record['856']['u']
    output_handler.report_of_self_ddas_to_hide(bib_source_of_input.platform, title, url)

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
        data = '; '.join(m.id + ' (' + m.source + ')' for m in matches_on_this_platform)
        output_handler.ambiguous(marc_record, "There are multiple matches on this platform. " + data)
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
    #ignore_depending_on_publisher,
    ignore_if_new_record_is_dda_and_better_is_available,
    update_same_dda_record_if_unambiguous,
    mark_as_ambiguous_new_record_is_dda_and_better_is_not_available,
    add_if_all_matches_are_on_other_platforms,
    update_same_platform_match_if_unambiguous,
]

def get_match_field(bib_source):
    """

    :param bib_source:
    :return:
    """
    if bib_source.id in ('68', '87', '67', '76', '66', '1', '91', '93', '41'):
        return '035'
    else:
        return '020'

def process_input_file(eg_records, reader, output_handler, bib_source_of_input, bibsources, match_field):
    """

    :type eg_records: dict[str, list[Record]]
    :type reader: MARCReader
    :type output_handler: OutputRecordHandler
    :type bib_source_of_input: BibSource
    :type bibsources: BibSourceRegistry
    :type match_field: str
    :return: int
    """
    records_processed_count = 0
    for marc_record in reader:
        # Convert record encoding to UTF-8 in leader. TODO: put in marc output handler.
        marc_record.leader = marc_record.leader[0:9] + 'a' + marc_record.leader[10:]
        records_processed_count += 1

        # Ensure record has 856:
        if not marc_record['856']:
            print("UH OH! AT LEAST ONE RECORD EXISTS WITH NO 856! at record no " + str(records_processed_count), file=sys.stderr)
            sys.exit(1)

        # match_field = get_match_field(bib_source_of_input)
        matches = match_marc_record_against_bib_data(eg_records, marc_record, match_field)
        # Matches is "False" if identifier not found; a set of matches (may be empty) otherwise.
        if matches == False:
            print("UH OH! AT LEAST ONE RECORD EXISTS WITH NO %s identifier! at record no %d" % (match_field, records_processed_count), file=sys.stderr)
            output_handler.ambiguous(marc_record, "Record has no identifier in %s." % (match_field,))
            continue
        if len(matches) == 0:
            output_handler.no_match(marc_record)
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
                output_handler.ambiguous(marc_record, "One or more match but no rules matched.")

    return records_processed_count


bibsource_match_histogram = {}


def match_marc_record_against_bib_data(eg_records, record, match_field):
    """

    :type eg_records: dict[str, list[Record]]
    :type record: pymarc.Record
    :type match_field: str
    :return: bool or set
    """
    # Matches will contain matching existing records.
    matches = set()
    found_an_identifier = False
    # Loop over all fields and 'a','z' subfields.
    for f in record.get_fields(match_field):
        for subfield in ['a', 'z']:
            for value in f.get_subfields(subfield):
                if match_field == '020':
                    cleaned = value.strip()
                    cleaned = cleaned.split('(')[0]
                    incoming_identifier = cleaned.split(' ')[0]
                    # We did less cleaning on the incoming ISBNS: this is our chance to fix them!!
                    if len(incoming_identifier) not in [10, 13]:
                        print('Probably a bad isbn: ' + incoming_identifier)
                elif match_field == '035':
                    cleaned = value.replace('(',' ')
                    cleaned = cleaned.replace(')',' ')
                    cleaned = cleaned.lower()
                    incoming_identifier = cleaned.strip()
                # A valid identifier contains numbers.
                if any(i.isdigit() for i in incoming_identifier) and len(incoming_identifier) > 7:
                    found_an_identifier = True
                if incoming_identifier in eg_records:
                    matches |= set(eg_records[incoming_identifier])
    if not found_an_identifier:
        return False

    for match in matches:
        if match.source not in bibsource_match_histogram:
            bibsource_match_histogram[match.source] = 0
        bibsource_match_histogram[match.source] += 1
    return matches


def parse_cmd_line():
    parser = optparse.OptionParser(usage="%prog [options] INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-d", "--bib-data", dest="bib_data", default="bib-data.txt",
                      help="CSV file of Bib Data to use")
    parser.add_option("--bib-source-file", dest="bib_source_file", default=os.path.join(os.path.dirname(__file__), 'conf', 'bib_sources.csv'),
                      help="CSV file of Bib Sources to use. [default: %default]")
    parser.add_option("-s", "--bib-source", dest="bib_source",
                      help="Numerical id of bib source for this batch. If empty, will prompt for this.")
    parser.add_option("-x", "--excel", action="store_true", dest="excel", default=False,
                      help="Instead of a .mrc file, the input is a CSV file. Output will be a modified CSV file..")
    parser.add_option("-n", "--negate", action="store_true", dest="negate", default=False,
                      help="For an excel report, find matches NOT in a specific bibsource.")
    parser.add_option("-m", "--match-field", action="store_true", dest="match_field", default=False,
                      help="Marc tag to use as identifier. Options are '020' or '035'. Default depends on bibsource.")
    opts, args = parser.parse_args()

    if not os.path.exists(opts.bib_data):
        parser.error("Bib data file [%s] not found." % (opts.bib_data,))
    if not os.path.exists(opts.bib_source_file):
        parser.error("Bib source file [%s] not found." % (opts.bib_source,))

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.bib_source_file, opts.bib_source, opts.bib_data, opts.excel, opts.negate, opts.match_field, args


def main():
    bib_source_file_name, bib_source, bib_data_file_name, excel, negate, match_field, input_files = parse_cmd_line()

    # CONFIG:
    bibsources = BibSourceRegistry()
    bibsources.load_from_file(bib_source_file_name)
    if not bib_source:
        bib_source = input("Please enter the number of the bibsource:").strip()

    if bib_source not in bibsources:
        print("Bib source [%s] is not known to Marc-a-roni." % (bib_source,), file=sys.stderr)
        sys.exit(2)
    bib_source_of_input = bibsources.get_bib_source_by_id(bib_source)
    print("\nYou have chosen the [%s] Bib Source\n" % (bib_source_of_input.name,))

    print("Loading records from %s" % (bib_data_file_name))
    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(bib_data_file_name))
    print("File last modified: %s" % (mod_time))
    if mod_time < (datetime.datetime.now() - datetime.timedelta(hours=1)):
        input("WARNING! Bib data is really old. Press a key to continue, or Ctrl-D to cancel ")

    if not match_field:
        match_field = get_match_field(bib_source_of_input)
    eg_records = load_bib_data(bib_data_file_name, match_field)

    if excel:
        isbn_columns = input("Identifier (e.g. ISBN) column(s) separated by commas, counting from 0: ")
        match_input_files(input_files, bib_source_of_input, bibsources, eg_records, isbn_columns, negate)
        return
    print("Processing input files.")
    process_input_files(input_files, bib_source_of_input, bibsources, eg_records, match_field)


if __name__ == '__main__':
    main()
