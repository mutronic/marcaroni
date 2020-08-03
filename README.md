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

Create a file based off bib_sources.csv that contains all the bib sources and their licenses. The location of this file will be provided as a command-line option to the `bibmatcher.py` script.

Edit or copy the `bib_sources.csv` file to reflect the bibsources used. Each bibsource represents one "collection" and has a license and a platform. This way it is possible to have multiple collections on the same platform, and while the files provided may overlap, we will try to not have multiple records for the same book on the same platform. 

Note: Some sources, like OCLC, automatically combine the marc record delivery for resources with varying licenses. In this case, we consider this to be one "collection".

## Usage

Run `~/PATH-TO-MARCARONI/bibmatcher.py -b ~/bib-data.txt -s ~/PATH/TO/CUSTOM/bib_sources.csv' FILE.mrc` where FILE.mrc is the file to process, the `-b` option is the location of the bib data file, and the `-s` option is the location of the bib sources file.
