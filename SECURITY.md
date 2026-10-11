# Reporting a problem

**A defect in the software.** Report it through the repository's private vulnerability
reporting, or as an issue where the problem is not sensitive. Include the input that
triggered it: the analysis is deterministic for a fixed input, contract version and software
version, so a reproducer usually is the whole report.

**A disagreement about the mathematics, the bounds or a number in the article.** File it as a
scientific-validation issue, not as a vulnerability. It is not a security matter and routing
it as one delays it. `CONTRIBUTING.md` says what such a change has to carry.

**Something that should not be in this package.** Report privately: a file that may not be
redistributed, a record that identifies a person, or anything else whose presence is itself
the problem. `data/LICENSES.md` states what may be redistributed and on whose terms.

## What this software does not expose

MIC-50-90 reads reported summaries, not records. It opens no network connection except in the
named download scripts, runs no code from its input, and writes only where it is told to.
**Do not submit identifiable or confidential patient-level records.** The package needs none.

It is not a clinical decision tool. `NOTICE.md` carries the complete scientific-use
limitation and is the file to read before using any result.
