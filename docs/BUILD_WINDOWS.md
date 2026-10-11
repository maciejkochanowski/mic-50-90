# Build and check the Windows application

Run these commands from the extracted software source directory on Windows
with Python 3.12. These are the versions used for the supplied executable. Use
a separate environment and a new output directory. The installed CLI is also
checked with Python 3.11 and 3.13 using compatible dependency versions.

```text
python -m venv build-env
build-env\Scripts\python -m pip install PyInstaller==6.22.3 numpy==2.5.3 scipy==1.18.1
build-env\Scripts\python tools/build_windows.py --output build/windows
```

The portable application is `build/windows/application/MIC-50-90/MIC-50-90.exe`.
Keep the entire `MIC-50-90` folder together. No Python installation is needed
to run it. The build copies the local form, plotting scripts and licensed fonts
explicitly and compares every bundled resource with its source. `BUILD_RECEIPT.json`
records source files, dependencies and executable contents. A successful build
alone does not establish correct execution.

Launch the executable, open a supplied analysis, calculate and save its report.
Then test the executable against an installed CLI package:

```text
python tools/check_interfaces.py --application build/windows/application/MIC-50-90/MIC-50-90.exe --examples .. --output build/interface-checks
```

Here `..` is a separately prepared interface-fixture folder containing `inputs/` and `windows/`; this optional eleven-case helper requires those external fixtures. The helper
compares eleven analyses and records the specific timing fields it excludes.
For automated form, saved-analysis and offline export checks, install Playwright
for Node.js, provide Chrome and run `python tools/check_browser.py --help`.
The browser helper accepts an explicit executable and keeps screenshots and
machine-readable outcomes. It does not modify the scientific input files.

This is a portable local build, not a signed Windows installer. Signing is separate from the build and execution checks.
