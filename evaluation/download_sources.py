"""Download the public isolate-level files of the confirmation data and check their SHA-256 values.

The files are U.S. federal public data (FDA NARMS and FDA animal-pathogen data). They are saved in
evaluation/sources/ (or --sources DIR) under the names below. A file whose checksum differs from
the recorded value is kept under its name with the suffix .new and reported, because the agencies
update these workbooks; prepare_benchmark.py reads only files with the recorded checksums.
"""
from __future__ import annotations

import common

import argparse
import hashlib
import urllib.request
from pathlib import Path

from common import HERE

SOURCES = {
    'narms_retail_meats.xlsx': ('https://www.fda.gov/files/animal%20%26%20veterinary/published/cvm-narms-retail-meats_0.xlsx',
                                'a989afc9daa0a41b116425524b1e541fdccb09498d7897423f2fec3d3afeb336'),
    'narms_haccp_1997_2005.xlsx': ('https://www.fda.gov/media/93333/download?attachment',
                                   '2ea802291579abe196846ccf158cebe7a2baea494a28f6c55a771bab9fe449ba'),
    'narms_haccp_2006_present.xlsx': ('https://www.fda.gov/media/93344/download?attachment',
                                      'c8cb8dd19b32f6f488de20cfbae6113a211137ae7b8f4c7216d0fd2182c3ec4e'),
    'narms_cecal_2013_present.xlsx': ('https://www.fda.gov/media/93351/download?attachment',
                                      '116831649876a47623040f76d50f806d2ac9940fde3a9983187159452696d7af'),
    'narms_minor_species_2020_2022.xlsx': ('https://www.fda.gov/media/183419/download?attachment',
                                           '469611094b535a5685b916a68617c207c19de777ee3004e0f723949d77fca3e6'),
    'fda_animal_pathogen_2017_2024.xlsx': ('https://www.fda.gov/media/132928/download?attachment',
                                           'a24fc9cdb30b47b94d81c3592f8a1d5b162bd37cd0da2ec38a4d11c4eb27ca97'),
}
DEFAULT = HERE / 'sources'
AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sources', type=Path, default=DEFAULT, help='folder for the files (default: evaluation/sources)')
    args = parser.parse_args()
    args.sources.mkdir(parents=True, exist_ok=True)
    status = 0
    for name, (url, expected) in SOURCES.items():
        path = args.sources / name
        if path.exists() and digest(path) == expected:
            print(f'{name}: present, checksum matches')
            continue
        request = urllib.request.Request(url, headers={'User-Agent': AGENT})
        with urllib.request.urlopen(request, timeout=600) as response:
            data = response.read()
        found = hashlib.sha256(data).hexdigest()
        if found == expected:
            path.write_bytes(data)
            print(f'{name}: downloaded, checksum matches')
        else:
            path.with_name(name + '.new').write_bytes(data)
            print(f'{name}: the agency file has changed (SHA-256 {found}); saved as {name}.new, not used')
            status = 1
    raise SystemExit(status)


if __name__ == '__main__':
    main()
