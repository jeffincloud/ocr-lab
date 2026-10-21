# passport-gen

Synthetic ICAO 9303 TD3 passports with ground truth, for load tests and accuracy SLIs.
All data is random and fictional; layouts carry no real state's design.

```bash
python tools/passport-gen/generate.py --count 500 --out loadtest/data/passports
```

Output: `passport-NNNNN.png` (ground truth embedded as PNG tEXt `ocr_truth`, which `apps/mock-llm`
reads to answer correctly) and `manifest.jsonl` (`file`, `width`, `height`, `truth`), which k6 uses
to score responses. Requires Pillow; uses DejaVu/Liberation fonts when present.
