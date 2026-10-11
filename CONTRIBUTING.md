# Contributing

Report a problem with the software version, command or Windows task, input needed to reproduce it, expected result and actual result. Remove private data from examples before sharing them.

## Check a change

Use Python 3.11–3.13 and Node.js 22. In a separate Python environment, from the source directory:

```text
python -m pip install -e ".[test]"
python -m pytest
node --test "tests/*.cjs"
```

Use an independent calculation or a small enumerated example when changing a numerical result. Add a regression test for a reproduced defect. Test counts and supported platforms are recorded by the completed Actions run rather than fixed in this guide.

## Preserve the input and result contracts

Keep schemas, parsers, examples, exports and documentation consistent. Existing supported input files must retain their meaning. Explain a necessary change to a public contract and provide an explicit migration path.

Keep finite-sample bounds, population confidence and study-unit calibration separate. Their sampling requirements and guarantees differ. Additional analyses must retain their declared assumptions and completion status.

## Build a distribution

See [Windows build instructions](docs/BUILD_WINDOWS.md) and [distribution policy](docs/DISTRIBUTION_POLICY.md). GitHub Actions builds and checks the downloadable Windows and CLI packages from the selected source commit. An existing published release is verified, not silently replaced.

Report security issues as described in [SECURITY.md](SECURITY.md).
