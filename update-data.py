#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

import psycopg2, sys, os.path

conn = psycopg2.connect("host=XXXX dbname=XXXX user=XXXX password=XXXX")
cur = conn.cursor()


output = open('bib-data.txt', 'w')
output.write('isbn,id,source\n')
errors = open('shitty-isbns.txt','w')

#cur.copy_expert("COPY (SELECT bre.id, bre.source, rfr.value FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND rfr.tag = '020' AND rfr.subfield in ('a','z') and bre.source is not NULL) TO STDOUT WITH CSV HEADER", data_dictionary)
cur.execute("SELECT bre.id, bre.source, rfr.value FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND rfr.tag = '020' AND rfr.subfield in ('a','z') and bre.source is not NULL")

for row in cur:
  cleaned = row[2].strip()
  isbn = cleaned.split(' ')[0]
  isbn = isbn.strip('-')
  isbn = isbn.split('ü')[0] ## Delete me when umlauts are fixed
  isbn = isbn.split('(')[0]
  isbn = isbn.split('\\')[0]
  ## If ISBN is the wrong length, warn but don't break
  if len(isbn) != 10 and len(isbn) != 13:
    #print("We probably have not found a good isbn here: " + cleaned)
    errors.write(','.join(map(str,row)))
    errors.write('\n')
  ## Only consider matchable isbns strings that are between 9 and 14 chars.
  if len(isbn) > 8 and len(isbn) < 15:
    output.write(','.join((str(isbn),str(row[0]),str(row[1]))))
    output.write('\n')

exit()


eg_records = []
# It's useful for us to see what shitty info is in the database.

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

  if len(eg_records) == 0:
    print("Data file did not contain valid records.")

data_dictionary.close()
errors.close()
