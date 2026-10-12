# Validation

The source comparison pipeline passes ten automated tests covering coordinate
placement and scale, exposure polarity, exact and tolerant subtraction,
metadata and filename matching, extra inner layers, explicit maps, missing
layers, archives, explicit translation and complete output publication.

The tool has also been exercised against a real four-layer board. Its exact
rendered masks match the original comparison pixel-for-pixel. The all-artwork
mode successfully processed twelve exported layers, including masks, paste,
silkscreen, outline and documentation.

Every GitHub Actions Windows build runs comparisons through both packaged
executables before making them available. The graphical self-test initializes
Tcl/Tk, fills input fields, invokes Compare, waits for the actual worker to
finish and checks the resulting images, report and enabled report button.
The command-line self-test verifies version reporting and a known artwork edit.

The local Codex sandbox could not initialize the system Tcl/Tk runtime, so the
packaged Windows checks run on a fresh GitHub-hosted Windows runner instead.
Actual RAR extraction with an external utility remains untested; ZIP input and
ZIP archives named .rar are covered by the automated tests. Excellon drill
files and electrical connectivity are outside the current comparison scope.
