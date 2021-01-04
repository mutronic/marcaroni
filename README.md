# marcaroni

## Requirements

This is a [Python 3](https://www.python.org/) script for Mac OSX that relies on the Python standard library, plus the following contributed libraries:
* psycopg2 (`pip install psycopg2-binary`)
* pymarc (`pip install pymarc`)
* isbnlib (`pip install isbnlib`)

It connects directly to the database of an Evergreen ILS, and assumes the use of  the "Bib Source" field to distinguish between eBook collections. It will therefore require read access to the Evergreen database (at least schemas `biblio` and `metabib`).

## Configuration

Copy the configuration file, .marcaroni.ini.sample, and edit the values to connect to your Evergreen database. Rename it to .marcaroni.ini and place it within the conf/ directory, or in your user's home directory (as `~/.marcaroni.ini`).

Somewhere (e.g. also in your home directory) run `update-data.py`. This will create a file in that directory, `bib-data.txt`, containing all identifiers (MARC fields 020 and 035) for active records in the database. This may be large - for a database with ~700,000 records, the file size is ~150MB. The location of this data file will be provided as a command-line option to the `bibmatcher.py` script.

If not using the included bib source list (conf/bib_sources.csv), create a modified version of that file containing information about your bibsources. The location of this file must be provided as a command-line option to the `bibmatcher.py` script.

Each bibsource represents one "collection" and has a license and a platform. This way it is possible to have multiple collections on the same platform, and while the files provided may overlap, we will try to not have multiple records for the same item on the same platform. 

Note: Some sources, like OCLC, automatically combine the marc record delivery for resources with varying licenses. In this case, we consider this to be one "collection".

## Usage

Update the local database of identifiers by running `update-data.py`. For this example, this was done in the root directory `~` resulting in the file `~/bib-data.txt`.

In a directory containing the .mrc file to process, run `~/PATH-TO-MARCARONI/bibmatcher.py -d ~/bib-data.txt --bib-source-file ~/PATH/TO/CUSTOM/bib_sources.csv' FILE.mrc` where FILE.mrc is the file to process. The --bib-source-file option is optional. This will prompt you to enter the numeric value of the bib source to use for this batch. The bib source can also be provided as a command-line argument, e.g. `-s 51`.

The results are a folder containing several marc files. These are a partition of the original marc file - i.e. each marc record in the input file will be in one of these output mrc files.  

### Excel (CSV) processing

To process a csv file, such as a title list, run `bibmatcher.py` with the -x option. You will be prompted for the columns containing identifiers. For example, Proquest title lists include ISBNs in the second and third column, so you would enter `2,3` and hit the Enter key. 

The result will be another CSV file, with `-matched` appended to the original filename. The first column of the output CSV will contain either 'NULL' if no match on that bibsource was found, the bib id of the matching record if a single match on that bibsource was found, and 'multi:{}' if multiple records that matched were found in that same bibsource.
