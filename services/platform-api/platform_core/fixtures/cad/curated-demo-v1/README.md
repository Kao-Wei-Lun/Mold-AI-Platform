# Curated CAD Demo Corpus v1

All geometry in this directory is generated from `manifest.json`; no company or customer CAD is
included. The declared CC0-1.0 license applies to the synthetic fixture definitions. These models
and their review outcomes are Demo verification data, not engineering guidance.

Run `python manage.py seed_cad_demo` to reconcile the corpus, or add `--verify-only` to perform a
read-only integrity check. Automated smoke uploads belong to `automated-cad-smoke-v1`, and upload
examples supplied manually belong to `manual-cad-upload-v1`.
