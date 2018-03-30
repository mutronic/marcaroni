#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:
from pymarc.field import Field
from pymarc import MARCReader
import sys
import csv
import os

## CONFIG:
bibsource = input("Please enter the number of the bibsource:")
dda_bibsources = ['37','50','56']
this_platform_bibsources = ['37','42']


if len(sys.argv) < 2:
  print("Please provide a file argument.")
  exit()


## PREPARATION: Import the Evergreen Record data
## TODO: check the latest update date and prompt to re-load.
## Current structure: a list of objects.
class ISBN:
  def __init__(self, id, source, isbn):
    self.id = id
    self.source = source
    self.isbn = isbn

eg_records = []
# It's useful for us to see what shitty info is in the database.
errors = open('shitty-isbns.txt','w')

with open('bib-data.txt','r') as datafile:
  myreader = csv.DictReader(datafile, delimiter=',')
  next(myreader) # skip header
  for row in myreader:
    cleaned = row['value'].strip()
    isbn = cleaned.split(' ')[0]
    isbn = isbn.strip('-')
    isbn = isbn.split('ü')[0] ## Delete me when umlauts are fixed
    isbn = isbn.split('(')[0]
    isbn = isbn.split('\\')[0]

    ## If ISBN is the wrong length, warn but don't break
    if len(isbn) != 10 and len(isbn) != 13:
      #print("We probably have not found a good isbn here: " + cleaned)
      errors.write(','.join(row.values()))
      errors.write('\n')

    ## Only consider matchable isbns strings that are between 9 and 14 chars.
    if len(isbn) > 8 and len(isbn) < 15:
      isbn_obj = ISBN(row['id'], row['source'], isbn)
      eg_records.append(isbn_obj)
if len(eg_records) == 0:
  print("Data file did not contain valid records.")
  exit()

## 


for filename in sys.argv[1:]:
  stub = os.path.splitext(filename)[0]
  outfile_no_matches = open(stub + '-nomatches.mrc', 'bw')
  outfile_no_matches_this_platform = open(stub + '-nomatchesthisplatform.mrc', 'bw')
  outfile_updates = open(stub + '-updates.mrc', 'bw')
  outfile_same_vendor = open(stub + '-vendor.mrc', 'bw')
  outfile_dda_report = open(stub + '-dda.txt', 'w')
  outfile_duplicates = open(stub + '-dupes.mrc','bw')
  outfile_duplicates_report = open(stub + '-dupes.txt','w')
  with open(filename, 'rb') as handler:
    reader = MARCReader(handler)
    count = 0;
    new_record_matches = {}
    for record in reader:
      count += 1
      ## Set up a place to put matching record things.
      matches = []
      ## Get all ISBNs
      for f in record.get_fields('020'):
        for subfield in ['a','z']:
          if f[subfield]:
            cleaned = f[subfield].strip()
            new_isbn = cleaned.split(' ')[0]
            ## We did less cleaning on the incoming ISBNS: this is our chance to fix them!!
            if len(new_isbn) not in [10,13]:
              print('Probably a bad isbn: ' + new_isbn)
            m = [(x.id, x.source) for x in eg_records if x.isbn == new_isbn]
            matches += m
      matches = set(matches)
      
      ## Deal with matches.
      # print(matches)
      if len(matches) == 0:
        outfile_no_matches.write(record.as_marc())
      # Output marc file if no matches on this platform
      else:
        # find matches on the same bibsource:
        exact_matches = [x for x in matches if x[1] == bibsource]
        if len(exact_matches) == 1:
          record.add_field(
            Field(
              tag = '901',
              indicators = [' ',' '],
              subfields = [
                'c', exact_matches[0][0]
              ]
            )
          ) ## Get the record id if only one match.
          outfile_updates.write(record.as_marc())
        elif len(exact_matches) > 1:
          outfile_duplicates.write(record_as_marc()) ## If multiple matches, don't choose a bib id
          outfile_duplicates_report.write("Duplicates found in bibsource " + bibsource + ":\n")
          outfile_duplicates_report.write("  Record title: " + record['245'].value() + "\n")
          for exact_match in exact_matches:
            outfile_duplicates_report.write(','.join(exact_match))
          outfile_duplicates_report.write("\n=================\n")

        # Isolate those with no matches on this platform, therefore we want to update

        this_platform_matches = [x for x in matches if x[1] in this_platform_bibsources]
        if len(this_platform_matches) == 0:
          outfile_no_matches_this_platform.write(record.as_marc())
        # Isolate those with matches on the same platform but another license that we want to update to this license?
        # Isolate those with matches on the same platform but we DO NOT want to update the licenses (purchased)


        # BONUS: Find duplicates on other platforms

        # Find DDA matches
        dda_matches = [x for x in matches if x[1] in dda_bibsources]
        if len(dda_matches) > 0:
          outfile_dda_report.write("DDAs found for record title : " + record['245'].value() + "\n")
          for dda_match in dda_matches:
            outfile_dda_report.write(','.join(dda_match))
          outfile_duplicates_report.write("\n=================\n")

      new_record_matches[count] = matches
      
  outfile_no_matches.close()
  outfile_no_matches_this_platform.close()
  outfile_updates.close()
  outfile_same_vendor.close()
  outfile_dda_report.close()
  outfile_duplicates.close()
  outfile_duplicates_report.close()

print("Record count: " + str(count))

