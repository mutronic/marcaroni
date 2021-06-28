import logging
import os
import datetime
import csv
from pymarc.field import Field


class OutputRecordHandler:
    def __init__(self, prefix, bibsource_prefix):
        if not os.path.exists(prefix):
            os.makedirs(prefix)
        self.prefix = prefix
        self.matches_by_bibsource = {}

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
        self.exact_match_ids__file_name = os.path.join(prefix, bibsource_prefix + "_exact_match_ids.txt")
        self.exact_match_ids__file_pointer = open(self.exact_match_ids__file_name, "w")
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
        self.exact_match_ids__file_pointer.close()
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
        marc_rec.marc.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.match_has_worse_license__file_pointer.write(marc_rec.as_marc())
        self.match_has_worse_license__counter += 1

    def exact_match(self, marc_rec, bib_id):
        marc_rec.marc.add_field(Field(
            tag='901',
            indicators=[' ', ' '],
            subfields=['c', bib_id]
        ))
        self.exact_match__file_pointer.write(marc_rec.as_marc())
        self.exact_match_ids__file_pointer.write('{}\n'.format(bib_id))
        self.exact_match__counter += 1

    def match_is_better(self, marc_rec):
        self.match_has_better_license__file_pointer.write(marc_rec.as_marc())
        self.match_has_better_license__counter += 1

    def ambiguous(self, record, reason):
        self.ambiguous__file_pointer.write(record.as_marc())
        self.ambiguous_report__csv_writer.writerow((record.title, record.isbn, reason))
        self.ambiguous__counter += 1

    def report_of_ddas_to_hide(self, platform, title, bib_id):
        self.ddas_to_hide_report_writer.writerow((platform, title, bib_id))
        self.old_ddas_counter += 1

    def report_of_self_ddas_to_hide(self, platform, title, isbn):
        self.self_ddas_to_hide_report_writer.writerow((platform, title, '', isbn))
        self.self_ddas_counter += 1

    def count_matches_by_bibsource(self, matches):
        for match in matches:
            if match.source not in self.matches_by_bibsource:
                self.matches_by_bibsource[match.source] = 0
            self.matches_by_bibsource[match.source] += 1

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
        for source in sorted(self.matches_by_bibsource.keys(), reverse=True,
                             key=lambda x: self.matches_by_bibsource[x]):
            logging.info("\t%s\t%s: \t%d" % (source, bibsources.get_bib_source_by_id(source).name,
                                             self.matches_by_bibsource[source]))

    def logger(self, message):
        logging.info(message)