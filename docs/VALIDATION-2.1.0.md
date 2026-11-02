# NeuroWings 2.1.0 validation

The default output uses the eight YOLO pose landmarks in WingsDig order. Legacy generic refinement is disabled by default after visual comparison on a 36-wing scan showed landmark merging and systematic displacement. No new model training or accuracy certification is claimed.

Image coordinates are EXIF-normalized RGB shared by display and inference. TPS remains paired with the normalized image; batch mode exports both together. TPS writes use a temporary file plus atomic replacement, preserve fractional coordinates, support Unicode names, validate blocks, and support zero landmarks. GUI saves a fingerprint-bound .nw.json companion with model alternatives and manual edits.

Offline batch invocation:

    NeuroWings.exe --recognize INPUT.jpg --output OUTPUT_DIR

Exports normalized JPG, TPS, JSON landmarks and an annotated JPG. This mode does not load GPT settings or call external models.

Regression coverage: malformed TPS, atomic Unicode/fractional/empty save, EXIF dimensions, aggregate statistics, constant/out-of-range/zero-DsA cases, safe update URLs, lossless project recovery, boundary crops and repeated bounding-box resize. A 36-wing scan was recognized on macOS; all 288 landmarks were visually reviewed on five contact sheets, compared with the old refinement, and round-tripped through TPS. GUI/aggregate/XLSX smoke checks passed. Windows EXE validation is recorded separately with final artifacts.

The biological interpretation rules and externally hosted update service still require their own validation; a morphometric classification is not an independently calibrated probability.

Additional release fixes: render operations preserve wing order; missing model alternatives cannot silently change the source; trusted YOLO weights are checksum-verified in GUI as well as batch mode. Coincident, collinear, nonfinite and out-of-image landmarks are excluded from valid morphometrics. Pose confidence below 0.5 is rejected. XLSX export is atomic, uses openpyxl on all systems and does not modify TPS. Histogram labels retain original wing numbers. Batch overlays use Pillow at original image resolution to avoid a large Matplotlib allocation. Fifteen portable regression tests pass.
