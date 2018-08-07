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


def license_comparator(license_of_match, license_of_input):
    """
    This function tells you if the incoming (input) license is better than the existing
    because if so, we should update the record. But if not better, then we should leave it.

    :param license_of_match:
    :param license_of_input:
    :return: True if Match is preferred, False if match is equal or lesser
    """
    if KNOWN_LICENSES[license_of_match] > KNOWN_LICENSES[license_of_input]:
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
    :rtype: dict[str, list[Record]]
    """
    # Load the Evergreen Record data as a dict of Records indexed by identifier (i.e. isbn / oclc string)
    # TODO: check the latest update date and prompt to re-load.
    eg_records = {}
    with open(bib_data_file_name, 'r') as datafile:
        myreader = csv.DictReader(datafile, delimiter=',')
        next(myreader)  # skip header
        for row in myreader:
            if row['tag'] != match_field:
                continue
            identifier = row['identifier']
            record_tuple = Record(row['id'], row['source'])
            if identifier not in eg_records:
                eg_records[identifier] = []
            eg_records[identifier].append(record_tuple)
    if len(eg_records) == 0:
        print("ISBN file did not contain valid records.", file=sys.stderr)
        sys.exit(1)
    return eg_records


class OutputRecordHandler:
    def __init__(self, prefix, bibsource_prefix):
        if not os.path.exists(prefix):
          os.makedirs(prefix)
        self.prefix = prefix
        self.add_file_name = os.path.join(prefix, bibsource_prefix + "_to_add.mrc")
        self.add_file_fp = open(self.add_file_name, "wb")

        self.update_file_name = os.path.join(prefix, bibsource_prefix + "_to_update.mrc")
        self.update_file_fp = open(self.update_file_name, "wb")

        self.exact_match_file_name = os.path.join(prefix, bibsource_prefix + "_exact_matches_same_bibsource.mrc")
        self.exact_match_file_fp = open(self.exact_match_file_name, "wb")

        self.ambiguous_file_name = os.path.join(prefix, bibsource_prefix + "_ambiguous.mrc")
        self.ambiguous_file_fp = open(self.ambiguous_file_name, "wb")
        self.ambiguous_report_file_name = os.path.join(prefix, "report_ambiguous_records.csv")
        self.ambiguous_report_file_fp = open(self.ambiguous_report_file_name, "w")
        self.ambiguous_report_file_writer = csv.writer(self.ambiguous_report_file_fp)
        self.ambiguous_report_file_writer.writerow(('Title', 'ISBN', 'Reason'))

        self.ignore_because_have_better_file_name = os.path.join(prefix, bibsource_prefix + "_dont_load_we_have_better.mrc")
        self.ignore_because_have_better_file_fp = open(self.ignore_because_have_better_file_name, "wb")

        # Remove these - build a reporting script at some other point. Unlikely to match on record ID (035) across
        # distributor platcorms.
        self.ddas_to_hide_report_file_name = os.path.join(prefix, 'report_existing_dda_records_to_hide.csv')
        self.ddas_to_hide_report_fp = open(self.ddas_to_hide_report_file_name, "w")
        self.ddas_to_hide_report_writer = csv.writer(self.ddas_to_hide_report_fp, dialect='excel-tab')
        # self.ddas_to_hide_report_writer.writerow(('Platform', 'Title', 'BibId'))

        self.self_ddas_to_hide_report_file_name = os.path.join(prefix, 'report_ddas_from_this_file_to_hide.csv')
        self.self_ddas_to_hide_report_fp = open(self.self_ddas_to_hide_report_file_name, "w")
        self.self_ddas_to_hide_report_writer = csv.writer(self.self_ddas_to_hide_report_fp, dialect='excel-tab')
        # self.self_ddas_to_hide_report_writer.writerow(('Platform','Title', 'BibId', '856'))

        self.add_counter = 0
        self.update_counter = 0
        self.exact_match_counter = 0
        self.ignore_counter = 0
        self.ambiguous_counter = 0

        self.old_ddas_counter = 0
        self.self_ddas_counter = 0

        # Initialize logging
        log_level = logging.INFO
        log_format = '  %(message)s'
        handlers = [logging.FileHandler(os.path.join(prefix, 'marcaroni.log')), logging.StreamHandler()]
        logging.basicConfig(level = log_level, format = log_format, handlers = handlers)
        logging.info("\nStarting Marcaroni: %s" %(datetime.datetime.now(), ) )

    def __del__(self):
        self.add_file_fp.close()
        self.update_file_fp.close()
        self.exact_match_file_fp.close()
        self.ignore_because_have_better_file_fp.close()
        self.ambiguous_file_fp.close()
        self.ddas_to_hide_report_fp.close()
        self.self_ddas_to_hide_report_fp.close()
        if self.add_counter == 0:
            os.remove(self.add_file_name)
        if self.update_counter == 0:
            os.remove(self.update_file_name)
        if self.exact_match_counter == 0:
            os.remove(self.exact_match_file_name)
        if self.ignore_counter == 0:
            os.remove(self.ignore_because_have_better_file_name)
        if self.ambiguous_counter == 0:
            os.remove(self.ambiguous_file_name)
            os.remove(self.ambiguous_report_file_name)
        if self.old_ddas_counter == 0:
            os.remove(self.ddas_to_hide_report_file_name)
        if self.self_ddas_counter == 0:
            os.remove(self.self_ddas_to_hide_report_file_name)

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

    def exact_match(self, marc_rec, bib_id):
        marc_rec.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.exact_match_file_fp.write(marc_rec.as_marc())
        self.exact_match_counter += 1

    def ignore(self, marc_rec):
        self.ignore_because_have_better_file_fp.write(marc_rec.as_marc())
        self.ignore_counter += 1

    def report_of_ddas_to_hide(self, platform, title, bib_id):
        self.ddas_to_hide_report_writer.writerow((platform, title, bib_id))
        self.old_ddas_counter += 1

    def report_of_self_ddas_to_hide(self, platform, title, isbn):
        self.self_ddas_to_hide_report_writer.writerow((platform, title, '', isbn))
        self.self_ddas_counter += 1

    def print_report(self, bibsources, count):
        logging.info("Record count: " + str(count))
        logging.info("Number of records to add:         %d" % (self.add_counter,))
        logging.info("Number of records to update:      %d" % (self.update_counter,))
        logging.info("Number of exact matches:          %d" % (self.exact_match_counter,))
        logging.info("Number of records to ignore:      %d" % (self.ignore_counter,))
        logging.info("Number of records to figure out:  %d" % (self.ambiguous_counter,))
        if (self.old_ddas_counter > 0):
            logging.info("DDAs that need to be deleted: \t%d" % (self.old_ddas_counter))

        if (self.self_ddas_counter > 0):
            logging.info("DDAs from this batch that need to be deactivated: %d" % (self.self_ddas_counter))

        logging.info("\nMatches per Bibsource:")
        logging.info("\tsource\tname\tcount(records)")
        for source in sorted(bibsource_match_histogram.keys(), reverse=True,
                             key=lambda x: bibsource_match_histogram[x]):
            logging.info("\t%s\t%s: \t%d" % (source, bibsources.get_bib_source_by_id(source).name,
                                      bibsource_match_histogram[source]))

    def logger(self, message):
        logging.info(message)


def process_input_files(input_files, bib_source_of_input, bibsources, eg_records):
    output_handler = None
    bibsource_prefix = re.sub('[^A-Za-z0-9]','_',bib_source_of_input.name)
    for filename in input_files:
        if output_handler is None:
            output_handler = OutputRecordHandler(prefix=os.path.splitext(filename)[0], bibsource_prefix=bibsource_prefix)
        with open(filename, 'rb') as handler:
            if output_handler is not None:
                output_handler.logger("Bibsource: %s"%(bib_source_of_input.name))
            reader = MARCReader(handler, to_unicode=True)
            count = process_input_file(eg_records, reader, output_handler, bib_source_of_input, bibsources)
            if output_handler is not None:
                output_handler.print_report(bibsources, count)


def match_input_files(input_files, bib_source_of_input, eg_records, isbn_column, negate):
    '''
    This function is for the Excel matching.

    :param input_files:
    :param bib_source_of_input:
    :param eg_records:
    :param isbn_column: str
    :return:
    '''
    cols = [int(x) for x in isbn_column.split(',')]
    for filename in input_files:
        prefix = os.path.splitext(filename)[0]
        outfile = open(prefix + '-matched.csv', 'w')
        out_writer = csv.writer(outfile)
        with open(filename, 'r') as handler:
            reader = csv.reader(handler)

            # Prep the output file with the header row.
            headerrow = next(reader)
            if len(headerrow) < 2:
                reader = csv.reader(handler, delimiter='\t')
                headerrow = next(reader)
            headerrow.insert(0,"BibID")
            out_writer.writerow(headerrow)

            bibsource_match_histogram = {}
            counter = {'none':0, 'one':0, 'multi':0}
            for row in reader:
                matches = set()
                for isbn_column in cols:
                    isbns = []
                    raw = row[isbn_column].strip('"=')
                    isbns.append(raw)

                    # Transform to ISBN 10 or 13.
                    if isbnlib.is_isbn13(raw):
                        isbns.append(isbnlib.to_isbn10(raw))
                    elif isbnlib.is_isbn10(raw):
                        isbns.append(isbnlib.to_isbn13(raw))

                    for isbn in isbns:
                        if isbn in eg_records:
                            matches |= set(eg_records[isbn])
                if negate:
                    desired_source_matches = [x for x in matches if x.source != bib_source_of_input.id]

                else:
                    desired_source_matches = [x for x in matches if x.source == bib_source_of_input.id]
#                print([(x.id, x.source) for x in same_source_matches])
                for x in desired_source_matches:
                    if x.source not in bibsource_match_histogram:
                        bibsource_match_histogram[x.source] = 0
                    bibsource_match_histogram[x.source] += 1
                if len(desired_source_matches) == 0:
                    counter['none'] += 1
                    row.insert(0, "NULL")
                    out_writer.writerow(row)
                elif len(desired_source_matches) == 1:
                    counter['one'] += 1
                    row.insert(0, desired_source_matches[0].id)
                    out_writer.writerow(row)
                else:
                    counter['multi'] += 1
                    note = "multi: " + ','.join([x.id for x in desired_source_matches])
                    row.insert(0, note)
                    out_writer.writerow(row)

        outfile.close()
        for key, value in counter.items():
            print(key + ': ' + str(value))

        print("\nMatches per Bibsource:")
        print("\tsource\tcount(records)")
        for source in sorted(bibsource_match_histogram.keys(), reverse=True,
                             key=lambda x: bibsource_match_histogram[x]):
            print("\t%s: \t%d" % (source, bibsource_match_histogram[source]))


def no_op_filter_predicate(remaining_matches, bib_source_of_inputs, bibsources, marc_record):
    return remaining_matches


FILTER_PREDICATES = [
    no_op_filter_predicate,
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
        output_handler.report_of_ddas_to_hide(bib_source.platform, title, m.id)

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
        data = '; '.join(m.id + ' (' + m.source + ')' for m in matches_on_this_platform)
        output_handler.ambiguous(marc_record, "There are multiple matches on this platform. " + data)
        return True
    single_match = matches_on_this_platform[0]
    if single_match.source == bib_source_of_input.id:
        output_handler.exact_match(marc_record, single_match.id)
        return True
    if predicate_vectors[single_match].match_is_better_license:
        output_handler.ignore(marc_record)
        return True
    output_handler.update(marc_record, single_match.id)
    return True


RULES = [
    ambiguous_if_matches_on_ambiguous_bibsource,
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
    if bib_source.id in ('68', '87', '67', '76', '66'):
        return '035'
    else:
        return '020'

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
        # Convert record encoding to UTF-8.
        marc_record.leader = marc_record.leader[0:9] + 'a' + marc_record.leader[10:]
        count += 1
        # Ensure record has 856:
        if not marc_record['856']:
            print("UH OH! AT LEAST ONE RECORD EXISTS WITH NO 856! at record no " + str(count), file=sys.stderr)
            sys.exit(1)
        match_field = get_match_field(bib_source_of_input)
        matches = match_marc_record_against_bib_data(eg_records, marc_record, match_field)
        if matches == False:
            print("UH OH! AT LEAST ONE RECORD EXISTS WITH NO %s identifier! at record no %d" % (match_field, count), file=sys.stderr)
            output_handler.ambiguous(marc_record, "Record has no identifier in %s." % (match_field,))
            continue
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
                output_handler.ambiguous(marc_record, "One or more match but no rules matched.")

    return count


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
    parser = optparse.OptionParser(usage="%prog INPUT_FILE [ ... INPUT_FILE_N ]")
    parser.add_option("-b", "--bib-data", dest="bib_data", default="bib-data.txt",
                      help="CSV file of Bib Data to use")
    parser.add_option("-s", "--bib-source", dest="bib_source", default="bib_sources.csv",
                      help="CSV file of Bib Sources to use")
    parser.add_option("-x", "--excel", action="store_true", dest="excel", default=False,
                      help="Input an excel file and find matches.")
    parser.add_option("-n", "--negate", action="store_true", dest="negate", default=False,
                      help="For an excel report, find matches NOT in a specific bibsource.")
    opts, args = parser.parse_args()

    if not os.path.exists(opts.bib_data):
        parser.error("Bib data file [%s] not found." % (opts.bib_data,))
    if not os.path.exists(opts.bib_source):
        parser.error("Bib source file [%s] not found." % (opts.bib_source,))

    if len(args) < 1:
        parser.error("Need at least one input file on command line.")
    return opts.bib_source, opts.bib_data, opts.excel, opts.negate, args


def main():
    bib_source_file_name, bib_data_file_name, excel, negate, input_files = parse_cmd_line()

    # CONFIG:
    bibsources = BibSourceRegistry()
    bibsources.load_from_file(bib_source_file_name)
    bibsource = input("Please enter the number of the bibsource:").strip()

    if bibsource not in bibsources:
        print("Bib source [%s] is not known to Marc-a-roni." % (bibsource,), file=sys.stderr)
        sys.exit(2)
    bib_source_of_input = bibsources.get_bib_source_by_id(bibsource)
    print("\nYou have chosen the [%s] Bib Source\n" % (bib_source_of_input.name,))

    match_field = get_match_field(bib_source_of_input)

    print("Loading records from %s" % (bib_data_file_name))
    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(bib_data_file_name))
    print("File last modified: %s" % (mod_time))
    if mod_time < (datetime.datetime.now() - datetime.timedelta(hours=1)):
        input("WARNING! Bib data is really old. Press a key to continue, or Ctrl-D to cancel ")

    eg_records = load_bib_data(bib_data_file_name, match_field)

    if excel:
        isbn_column = input("ISBN column(s), counting from 0: ")
        match_input_files(input_files, bib_source_of_input, eg_records, isbn_column, negate)
        return
    print("Processing input files.")
    process_input_files(input_files, bib_source_of_input, bibsources, eg_records)


if __name__ == '__main__':
    main()
