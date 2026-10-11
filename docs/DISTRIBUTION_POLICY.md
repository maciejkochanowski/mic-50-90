# Public software distribution

GitHub, PyPI and software deposits on Zenodo contain code and directly related materials: runtime code, the local application, build and test configuration, test suites, small example inputs, user documentation, licences, formal proof source code and software verification records. Mathematical documentation explains the implemented calculations and how to check them.

The following remain outside these platforms:

- The manuscript and all supplementary appendices, in every source and rendered format.
- Editorial figures, screenshots prepared for the appendices, document templates and article-generation inputs.
- Research campaign narratives, editorial audits and generators whose purpose is to assemble the article or its supporting research report.
- The complete local article/research delivery ZIP or any nested archive containing the excluded documents.

Release assets must be built and uploaded by GitHub Actions from the selected software source commit. A software deposit must use these checked assets or that source tag. Do not upload the local combined article package.

Python packaging excludes editorial directories and article-specific filenames explicitly. The release content checker rejects excluded files rather than silently dropping them from an unchecked archive. Code that generates user analysis reports, ordinary example inputs and independent numerical checks remains part of the software.

Third-party data and fonts keep their source terms. See DATA_TERMS.md and ../data/LICENSES.md. Excluding publication files does not remove mathematical explanations or independent checks from the software documentation.
