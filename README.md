# PCB Diff

Compare two Gerber exports and save images of every matched layer. Inputs can be
two ZIP/RAR archives, two folders, or two individual Gerber files. All processing
is local. The tool includes a file-picker interface and a command-line interface.

## Windows setup

Download the portable Windows ZIP from
[GitHub Releases](https://github.com/weiliangng/pcb-diff/releases/latest), extract
it, and run **PCB-Diff.exe**. The executable includes Python, the renderer and
Tcl/Tk, so no Python installation is needed. **pcb-diff-cli.exe** provides the
same comparison through a terminal:

```powershell
.\pcb-diff-cli.exe "older.zip" "newer.zip" -o "comparison"
```

For running or modifying the Python source:

1. Install Python 3.12 or newer from [python.org](https://www.python.org/downloads/).
2. Extract this whole tool folder, then run `setup-windows.cmd` once. Setup downloads
   the pinned dependencies into a private `.venv` inside the tool folder.
3. Run `launch-windows.cmd`, choose older and newer inputs, choose where to save,
   and click **Compare**. Click **Open report** when finished.

The tool makes no network requests when comparing files. Real RAR archives need
7-Zip or UnRAR; ZIP archives with a `.rar` filename work without those programs.
Prefer ZIP for an installation with no additional archive utility.

## Command line

After Windows setup:

```powershell
.\.venv\Scripts\python.exe pcb_diff.py "older.zip" "newer.zip" -o "comparison"
```

On Windows, macOS or Linux with Python 3.12+:

```sh
python -m venv .venv
# Activate the environment using your platform's usual command.
python -m pip install -r requirements.txt
python pcb_diff.py older.zip newer.zip -o comparison
python pcb_diff.py older.gbr newer.gbr -o single-layer
python pcb_diff.py old-folder new-folder --scope all -o all-layers
python pcb_diff.py old.zip new.zip --dpmm 100 --tolerance-mm 0 -o high-resolution
python pcb_diff.py old.zip new.zip --layer-map examples/layer-map.json -o mapped
python pcb_diff.py --help
```

You can also install this folder with `python -m pip install .` to get the
`pcb-diff` and `pcb-diff-gui` commands. Linux GUI use may require your distribution's
`python3-tk` package. The command-line interface does not require Tkinter.

The output directory must be new or empty. The tool publishes it only after every
comparison succeeds, so completed results cannot be mixed with partial results.

## What gets saved

- `overview-exact.png`: all layers, with added artwork highlighted green and removed
  artwork highlighted red by default.
- `overview-tolerant.png`: the same comparison after excluding nearby edge differences.
- `<layer>-old.png`, `<layer>-new.png`: matching binary renders on the same canvas.
- `<layer>-diff-exact.png`, `<layer>-diff-tolerant.png`: full-resolution highlighted differences.
- `<layer>-added-mask.png`, `<layer>-removed-mask.png`: exact subtraction masks.
- `<layer>-added-tolerant-mask.png`, `<layer>-removed-tolerant-mask.png`: secondary masks.
- `<layer>-region-01.png`, etc.: full-resolution crops of the largest change groups.
- `report.html`: locally browsable report linking the images.
- `results.json`: input file hashes, settings, layer mapping, exclusions, physical
  bounds, area estimates and all detected change regions. Schema version is 1.

## Layer matching

There is no fixed layer count. Auto-matching prefers Gerber X2 `TF.FileFunction`
metadata, then known suffixes, then common KiCad names and EasyEDA layer comments.
The default scope selects copper. `--scope all` adds recognized mask, paste,
silkscreen, outline and documentation artwork.

Supported examples include `.GTL`, `.GBL`, `.G1` through any numbered inner `.Gn`,
`.GTS`, `.GBS`, `.GTO`, `.GBO`, `.GTP`, `.GBP`, `.GKO`, `.GDL`, `.GDD`,
Eagle `.cmp`/`.sol`, KiCad `F_Cu`, `B_Cu`, `InN_Cu`, `F_Mask`, `B_Mask`,
`F_Paste`, `B_Paste`, `F_Silkscreen`, `B_Silkscreen`, `Edge_Cuts`, and X2 roles.
`.GM1` is assumed to be a board outline; use a manual map if your exporter uses
it for a different mechanical layer.

Ambiguous duplicates, unknown Gerber roles, and missing counterparts stop the
automatic comparison. They are never silently paired by alphabetical order.
`--missing skip` explicitly excludes unmatched layers and records the exclusions.
`--missing empty` treats an absent layer as empty artwork and shows a whole layer
as added or removed.

For other exporters, edit a layer map. Paths are relative to the respective archive
root or input folder, including nested folders. A manual map overrides automatic
matching and scope; only its listed pairs are compared.

```json
{
  "layers": [
    {"name": "Top copper", "kind": "copper", "old": "old-top.gbr", "new": "new-top.gbr"},
    {"name": "Custom mechanical layer", "kind": "mechanical", "old": "mech-a.art", "new": "mech-b.art"}
  ]
}
```

Set one input to `null` to compare against empty artwork, together with
`--missing empty`. Two individually selected Gerber files are compared directly
regardless of filename; choose the corresponding layers yourself in that mode.

## Configurable settings

| Option | Default | Effect |
|---|---|---|
| `--scope` | `copper` | Copper only or all recognized artwork layers |
| `--layer-map` | automatic | Explicit pairs for custom naming or selected layers |
| `--missing` | `error` | Error, skip or compare against empty artwork |
| `--dpmm` | `50` | Pixels/mm; 50 means 20 µm/pixel |
| `--tolerance-mm` | `0.02` | Secondary Euclidean tolerance between pixel centres |
| `--tolerance-pixels` | unset | Alternative to physical tolerance |
| `--threshold` | `128` | Coverage threshold from 1 through 255 |
| `--new-offset-mm DX DY` | `0 0` | Explicit translation of all newer artwork |
| `--margin-mm` | `0.5` | Shared canvas margin |
| `--region-gap-mm` | `0.35` | Grouping radius for crops; never changes difference masks |
| `--crop-padding-mm` | `0.35` | Padding around each crop |
| `--max-crops` | `12` | Largest crops exported per layer; all regions remain in JSON |
| `--overview-columns` | `2` | Overview layout; independent of layer count |
| `--preview-width` | `1100` | Width limit of each overview layer image |
| `--palette` | provided palette | JSON colors; see `examples/palette.json` |
| `--max-megapixels` | `60` | Per-layer canvas limit to bound memory use |
| `--archive-tool` | discovered on PATH | 7-Zip/UnRAR executable for actual RAR input |

## What was hardcoded in the first script

| First script assumption | This export |
|---|---|
| Four copper suffixes: GTL, G1, G2, GBL | Any number of recognized inner layers; X2/common names and manual mapping |
| Matching only by extension | Metadata-first matching plus explicit maps |
| Windows Segoe font and WinRAR installation path | Pillow font fallback; archive utility on PATH or user-specified path |
| Green/red/gray/dark palette | `--palette` file |
| 128 coverage threshold | `--threshold` |
| 0.5 mm canvas margin | `--margin-mm` |
| 0.35 mm grouping/padding; 12 crops | Independent configurable options |
| Two-column, four-layer overview wording | Arbitrary layer count and configurable columns/preview size |
| One-pixel square tolerance | Physical Euclidean tolerance, or explicit pixel tolerance |
| Archives/folders only | Also accepts two individual Gerber files |
| Absolute coordinates only | Preserved by default; explicit newer-version translation available |
| Output files written into an existing folder | Complete results published to a new or empty folder |

Resolution and pixel tolerance were already adjustable. Neither version hardcodes
your board dimensions or component locations. Gerber parsing supplies the units,
apertures, exposure polarity and geometry. Comments and companion documents are
treated as input data, not instructions.

The edge-tolerant results differ slightly from the first export because the
secondary tolerance now uses Euclidean distance instead of a square pixel
neighborhood. Exact subtraction is unchanged at the same settings and canvas.

## Extension points and remaining limits

- `pcb_diff/layers.py`: add exporter filename rules, archive adapters, layer roles,
  or alternate pairing strategies. Explicit maps handle unusual names without code changes.
- `pcb_diff/core.py`: reusable `compare(...)` API, render backend, tolerance,
  region grouping, images, report and versioned results schema.
- `pcb_diff/cli.py` and `pcb_diff/gui.py`: separate interfaces to the same pipeline.

Planned extension candidates: Excellon drill differences, drill-hole subtraction,
fiducial-based alignment, explicit rotation/mirroring, vector/geometry comparison,
electrical connectivity checks, raster tiling for large panels, SVG/PDF output,
CI change thresholds and additional executable platforms. Those are not implemented
in this release.

This version compares rendered Gerber exposures, not nets. Bottom copper is viewed
from above without mirroring. Mask/paste exposures should be interpreted as their
Gerber artwork, not as copper. Gerber units are converted to millimetres.
Small changes below the selected raster resolution can be missed. Exact binary
differences include edge pixels affected by rasterization; the secondary tolerance
can suppress real edits close to an existing edge, which is why exact images and
masks are always retained.

Frames use the union of all selected artwork and detected outlines; no automatic
translation, rotation or mirroring is applied. Actual RAR extraction depends on
the user's installed archive utility. Source-folder inputs should contain one
export per folder. Copper layers without usable role information need a map.

## Validation

Run from this tool folder:

```sh
python -m unittest discover -s tests -v
```

Tests cover scale/absolute coordinates, exposure polarity, identical inputs,
Euclidean tolerance, metadata and filename matching, arbitrary inner-layer count,
duplicates/missing layers, manual maps, archive signatures, output publication,
explicit translation, missing-as-empty and canvas size limits.

Rendering dependencies: [Gerbonara](https://gerbolyze.gitlab.io/gerbonara/),
[resvg-py](https://pypi.org/project/resvg-py/), Pillow, NumPy and SciPy.
Dependencies retain their own licenses. Tool source is provided for inspection
and modification; no distribution license is assigned by this export.

## Build and release

On Windows with a working source environment, run `build-windows.cmd`, or:

```powershell
python -m pip install -r requirements-build.txt
python scripts/build_windows.py
```

The build tests the core, creates `PCB-Diff.exe` and `pcb-diff-cli.exe` with
PyInstaller, executes a comparison through each binary, builds a source archive
and Python wheel, and packages the results under `release-assets/`.
The GUI executable test drives the real hidden file-picker interface through
its Compare action and checks the completed output and report button.

GitHub Actions runs tests on Linux and Windows for every main-branch push and
pull request. It then builds and tests the Windows binaries and retains them as
workflow artifacts. Actions are pinned to commit SHAs, with Dependabot configured
to propose updates. No repository secrets need to be added for release publishing.

To publish a version:

1. Update `pcb_diff/__init__.py` and the project version in `pyproject.toml` together.
2. Commit the version change and push a matching tag, such as `v1.0.1`.
3. The **Release** workflow checks the tag, builds and tests both executables,
   verifies the checksums, uploads the assets to a draft, and publishes it only
   after all those steps succeed.

Alternatively, run the Release workflow manually from GitHub Actions, entering
the matching version tag. This also creates the tag at the selected commit if it
doesn't already exist. Published releases are never silently overwritten; bump
the version for changes. Draft uploads can be retried.

Release assets include the portable Windows ZIP, each standalone executable,
the wheel and source archive, dependency versions, third-party license notices
and `SHA256SUMS.txt`. These are Windows x64 builds. Executables are not code-signed;
Windows may show its usual warning for a newly downloaded unsigned application.
