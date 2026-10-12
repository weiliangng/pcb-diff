# Comparison examples

These PNGs are original PCB Diff outputs from the bank and SCV2 comparisons
illustrated in the example PDF reports. They were saved directly from the
matching comparison output folders rather than rasterized from the printed PDFs.

- `bank-overview.png`: exact top/bottom copper comparison for the two-layer bank board.
- `scv2-overview.png`: exact top/inner 1/inner 2/bottom copper comparison for SCV2.
- `scv2-routing-detail.png`: exact subtraction crop of SCV2 bottom-copper region 1.

Both runs used 50 pixels/mm, threshold 128/255, 0.02 mm secondary edge tolerance
and no coordinate offset. Green is added artwork, red is removed artwork, and
gray is unchanged artwork in the exact views. Images retain the original layer
geometry; areas are raster estimates. Gerber inputs are not included.
