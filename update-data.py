#!/usr/local/bin/python3
# vim: set expandtab:
# vim: tabstop=2:
# vim: ai:
# vim: shiftwidth=2:

from marcaroni import db

try:
    conn = db.connect()
    cur = conn.cursor()
except Exception as e:
    print("Update data could not connect.")
    exit(1)
else:
    output = open('bib-data.txt', 'w')
    output.write('identifier,id,source,tag,subfield\n')
    errors = open('shitty-isbns.txt','w')

    #debug
    print('Starting query...')
    #cur.copy_expert("COPY (SELECT bre.id, bre.source, rfr.value FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND rfr.tag = '020' AND rfr.subfield in ('a','z') and bre.source is not NULL) TO STDOUT WITH CSV HEADER", data_dictionary)
    cur.execute("SELECT bre.id, bre.source, rfr.value, rfr.tag, rfr.subfield FROM biblio.record_entry bre JOIN metabib.real_full_rec rfr ON bre.id = rfr.record WHERE not bre.deleted AND (rfr.tag = '020' OR  rfr.tag = '035') AND (rfr.subfield = 'a' OR rfr.subfield = 'z') and bre.source is not NULL")

    #debug
    print('Query finished. Cleaning data...')
    for row in cur:
      identifier = row[2].strip()
      identifier = identifier.strip(',')
      if str(row[3]) == '020':
          identifier = identifier.split(' ')[0]
          identifier = identifier.strip('-')
          identifier = identifier.split('ü')[0] ## Delete me when umlauts are fixed
          identifier = identifier.split('(')[0]
          identifier = identifier.split('\\')[0]
          ## If ISBN is the wrong length, warn but don't break
          if len(identifier) != 10 and len(identifier) != 13:
            #print("We probably have not found a good isbn here: " + cleaned)
            errors.write(','.join(map(str,row)))
            errors.write('\n')
          ## Only consider matchable isbns strings that are between 9 and 14 chars.
          if len(identifier) < 9 or len(identifier) > 14:
              continue
      else:
          if not any(i.isdigit() for i in identifier):
              continue
      if len(identifier) == 0:
          continue
      output.write(','.join((str(identifier), str(row[0]), str(row[1]), str(row[3]), str(row[4]))))
      output.write('\n')

    #debug
    print('Done.')

    exit()
