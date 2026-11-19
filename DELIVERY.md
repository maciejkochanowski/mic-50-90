# MIC-50-90 1.0.3 source delivery

This release contains the calculation engine, local browser application, tests,
examples, historical evaluation materials, formal algebra, verification tools and
usage documentation. Version 1.0.3 publishes a container image with each release; its
computations are those of 1.0.2, which included runtime and packaging corrections.
`PACKAGE_STATUS.json` describes the distribution policy; it does not contain the digest of an
archive that contains it.

## Identify the delivered bytes

Use the final external delivery receipt and `SHA256SUMS.txt` to identify each
archive before extracting or installing it. Archive hashes cannot be stored
self-consistently inside those same archives. A version label alone is not an
artifact identity. The GitHub release, its checksums and the Zenodo record
identify the published files.

The complete source bundle carries `PACKAGE_MANIFEST.sha256`, covering its source
selection. The standard Python sdist carries its own `MANIFEST.sha256`, generated
from its actual members, including build-generated `PKG-INFO`. Neither manifest
lists itself. The wheel uses its standard `RECORD` plus its external archive hash.

## Check an extracted distribution

With NumPy, SciPy and `jsonschema` installed, run from the extracted root:

```sh
python reproducibility/self_test.py
node --test 'tests/*.cjs'
```

The self-test checks imports, declared versions, shipped schemas and examples,
two controlled numerical/report cases and manifest integrity. If `jsonschema`
is absent, it explicitly reports that schema validation was not performed;
parsing alone is not a completed schema validation. Manifest checks fail if a
required digest is absent, malformed, duplicated or does not match its file.

For the complete source bundle, also run:

```sh
python scripts/refresh_package_manifest.py --check
```

This source-specific command is not the sdist check. Do not regenerate a
manifest to bypass a failed integrity check. The full Python suite is available
through `python -m pytest tests -q` after installing the `test` extra. Focused
packaging regressions build an actual sdist and check intentional damage.

## Read evidence at its recorded scope

Current validation is recorded outside the release by artifact hash, commands,
environments and outcomes. Historical Windows, Python-matrix, coverage, mutation,
calibration and formal-compilation evidence in `evaluation/` applies to its
recorded baseline. New checks do not silently replace adverse or interrupted
historical runs. A source build or Linux test does not verify a Windows executable.
The numerical domain and module-specific validation limits are documented in the
API documentation and `docs/VALIDATION_SCOPE.md`.

The manuscript, supplementary appendices and editorial files are separate from
this software distribution. The final delivery inventory records their identity
and status separately.
