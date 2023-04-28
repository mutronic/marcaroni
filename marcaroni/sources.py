#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

import csv

# noinspection PySetFunctionToLiteral
KNOWN_LICENSES = {
    'dda': 0,
    'eba': 1,
    'subscription': 2,
    'purchased': 3,
    'oa': 1,
}


class UnknownBibSourceLicense(Exception):
    pass


class DuplicateBibSource(Exception):
    pass


class BibSource:
    def __init__(self, bib_source_id, name, platform, bib_license):
        if bib_license not in KNOWN_LICENSES:
            raise UnknownBibSourceLicense("Bib Source License [%s] is not known" % (bib_license,))
        self.id = bib_source_id
        self.name = name
        self.platform = platform
        self.license = bib_license


class BibSourceRegistry:
    def __init__(self):
        self.bib_source_by_id = {}  # dict[str] = BibSource
        self.bib_source_by_platform = {}  # dict[str] = list[BibSource]
        self.selected = None

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
        """
        Get a bib source by numeric id

        :type bib_source_id: int
        :return BibSource:
        """
        return self.bib_source_by_id[bib_source_id]

    def __contains__(self, item):
        return item in self.bib_source_by_id

    def autosuggest(self, prompt):
        options = [[x.name, x.id] for x in self.bib_source_by_id.values() if prompt.lower() in x.name.lower()]
        return sorted(options)

    def set_selected(self, selected_id):
        self.selected = self.bib_source_by_id[selected_id]

    def other_sources_on_platform(self):
        if not self.selected:
            return False # Raise error?
        selected_platform = self.selected.platform
        source_ids = set([s.id for s in self.bib_source_by_id.values() if s.platform == selected_platform])
        source_ids.remove(self.selected.id)
        return source_ids

    def get_match_field(self, bib_source_id = None):
        if not bib_source_id:
            if not self.selected:
                return None
            else:
                bib_source_id = self.selected.id

        if bib_source_id in ('68', '87', '67', '76', '66', '1', '93', '41', '48', '49', '40', '71', '40', '22', '37', '102', '106'):
            return '035'
        if bib_source_id in ('91'):
            return '035'
        else:
            return '020'
