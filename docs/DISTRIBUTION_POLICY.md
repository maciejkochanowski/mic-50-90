# Public software distribution

GitHub, PyPI and software deposits on Zenodo contain code and directly related materials: runtime code, the Galaxy tool wrappers, build and test configuration, test suites, small example inputs, the evaluation inputs, scripts and result tables, the code that draws the figures from these results, user documentation, licenses, formal proof source code and software verification records. Mathematical documentation explains the implemented calculations and how to check them.

The following remain outside these platforms:

- The manuscript and all supplementary appendices, in every source and rendered format.
- Rendered figures, screenshots prepared for the appendices, document templates and article-generation inputs.
- Generators whose purpose is to assemble the article or its supplementary documents.

Release assets must be built and uploaded by GitHub Actions from the selected software source commit. A software deposit must use these checked assets or that source tag.

The source selection in `scripts/package_files.py` leaves out editorial directories and article-specific filenames. The release content checker in `tools/software_release.py` rejects such files rather than silently dropping them from an unchecked archive. Code that generates user analysis reports, ordinary example inputs and independent numerical checks remains part of the software.

Third-party data and fonts keep their source terms. See DATA_TERMS.md and ../data/LICENSES.md. Excluding publication files does not remove mathematical explanations or independent checks from the software documentation.
