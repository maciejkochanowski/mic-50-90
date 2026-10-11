# Scientific scope

MIC-50-90 1.0.0 is research software for incomplete MIC summaries and reporting audits.

Sharp finite-sample bounds are conditional on the correctness of the supplied panel, ranks, summaries and category semantics. They require no sampling model, but incorrect metadata can invalidate their interpretation. The iid population layer additionally requires iid sampling. The calibrated layer requires exchangeable study units and a reference/score protocol matching manifest 1.2; a global fallback is not a group-conditional guarantee.

A calibrated tail-containment event does not establish that the whole true distribution is in a Wasserstein ball. Complete category counts do not determine concentrations inside censored intervals. Assumption scenarios remain distinct from all three inferential layers.

The program does not infer clinical breakpoints, classify individual susceptibility or recommend treatment. It requires only aggregate information; identifiable patient records are unnecessary.

# Bundled typography

The desktop and exported reports embed web-font derivatives of CMU Serif,
CMU Typewriter, Latin Modern Math and DejaVu Sans. Their glyph outlines and
metrics match the source fonts used for the supplementary documents and plots.
The renamed MIC Web faces retain their original copyright notices. Font
licences and the source-to-web-file SHA-256 manifest are included in
`mic_50_90/gui_assets/fonts/`. These fonts require no system installation.
