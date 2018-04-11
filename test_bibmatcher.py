import unittest


import bibmatcher


class MockOutputRecordHandler(bibmatcher.OutputRecordHandler):
    # noinspection PyMissingConstructor
    def __init__(self):
        self.calls = []

    def __del__(self):
        pass

    def add(self, marc_rec):
        self.calls.append(('add', marc_rec))

    def ambiguous(self, marc_rec, reason):
        self.calls.append(('ambiguous', marc_rec, reason))

    def update(self, marc_rec, bib_id):
        self.calls.append(('update', marc_rec, bib_id))

    def ignore(self, marc_rec):
        self.calls.append(('ignore', marc_rec))

    def report_of_ddas_to_hide(self, title, platform, bib_id):
        self.calls.append(('report_of_ddas_to_hide', title, platform, bib_id))


class MARCRecord:
    pass


class MyTestCase(unittest.TestCase):
    @staticmethod
    def get_marc_record():
        return MARCRecord()

    @staticmethod
    def get_vectors(better_licensed=True, same_platform=False, length=3):
        v = {}
        for i in range(length):
            v[bibmatcher.Record(i, 1)] = bibmatcher.PredicateVector(
                match_is_better_license=better_licensed,
                match_is_dda=False,
                match_is_same_platform=same_platform
            )
        return v

    def test_ignore_if_new_record_is_dda_and_better_is_available_input_not_dda(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'purchased')
        output = MockOutputRecordHandler()

        self.assertFalse(bibmatcher.ignore_if_new_record_is_dda_and_better_is_available(
            self.get_marc_record(),
            input_bib_source,
            self.get_vectors(),
            output
        ))

    def test_ignore_if_new_record_is_dda_and_better_is_available_input_is_dda_better_is_avail(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()

        self.assertTrue(bibmatcher.ignore_if_new_record_is_dda_and_better_is_available(
            self.get_marc_record(),
            input_bib_source,
            self.get_vectors(),
            output
        ))
        self.assertEqual(len(output.calls), 1)
        self.assertEqual(output.calls[0][0], 'ignore')

    def test_ignore_if_new_record_is_dda_and_better_is_available_input_is_dda_better_is_not_avail(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()

        self.assertFalse(bibmatcher.ignore_if_new_record_is_dda_and_better_is_available(
            self.get_marc_record(),
            input_bib_source,
            self.get_vectors(better_licensed=False),
            output
        ))

    def test_update_same_platform_match_if_unambiguous_no_same_plat_match(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()

        self.assertFalse(bibmatcher.update_same_platform_match_if_unambiguous(
            self.get_marc_record(),
            input_bib_source,
            self.get_vectors(),
            output
        ))

    def test_update_same_platform_match_if_unambiguous_multiple_same_plat_match(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()

        self.assertTrue(bibmatcher.update_same_platform_match_if_unambiguous(
            self.get_marc_record(),
            input_bib_source,
            self.get_vectors(same_platform=True),
            output
        ))

        self.assertEqual(len(output.calls), 1)
        self.assertEqual(output.calls[0][0], 'ambiguous')

    def test_update_same_platform_match_if_unambiguous_one_same_plat_match_with_worse(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()
        v = self.get_vectors(same_platform=True, better_licensed=False, length=1)
        v.update(self.get_vectors(same_platform=False, length=2))

        self.assertTrue(bibmatcher.update_same_platform_match_if_unambiguous(
            self.get_marc_record(),
            input_bib_source,
            v,
            output
        ))

        self.assertEqual(len(output.calls), 1)
        self.assertEqual(output.calls[0][0], 'update')

    def test_update_same_platform_match_if_unambiguous_one_same_plat_match_with_better(self):
        input_bib_source = bibmatcher.BibSource(1, 'test', 'test_plat', 'dda')
        output = MockOutputRecordHandler()
        v = self.get_vectors(same_platform=True, better_licensed=True, length=1)
        v.update(self.get_vectors(same_platform=False, length=2))

        self.assertTrue(bibmatcher.update_same_platform_match_if_unambiguous(
            self.get_marc_record(),
            input_bib_source,
            v,
            output
        ))

        self.assertEqual(len(output.calls), 1)
        self.assertEqual(output.calls[0][0], 'ignore')


if __name__ == '__main__':
    unittest.main()
