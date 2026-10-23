# Noto Sans Math 3.000, subset

The math font for the formulas on the tool pages (MathML), so that fractions, roots,
scripts and stretching brackets lay out the same in every browser. Licensed under the
SIL Open Font License 1.1 (`OFL.txt`); Noto Sans Math has no reserved font name.

Source: Google Fonts, `https://fonts.googleapis.com/css2?family=Noto+Sans+Math`
(Version 3.000). Subset with fontTools, keeping the MATH table and its glyph variants:

```bash
python -m fontTools.subset NotoSansMath-Regular.woff2 --flavor=woff2 \
  --output-file=NotoSansMath-Regular-subset.woff2 \
  --layout-features='*' --name-IDs='*' --name-languages='*' --notdef-outline \
  --unicodes="U+0020-007E,U+00A0,U+00AC,U+00B1,U+00B7,U+00D7,U+00F7,U+0391-03A9,U+03B1-03C9,U+03D1,U+03D5,U+03D6,U+03F0,U+03F1,U+03F5,U+02C6,U+02C7,U+02D8-02DA,U+02DC,U+2016,U+2026,U+2032-2034,U+2044,U+2061-2064,U+2102,U+210E,U+2113,U+2115,U+211A,U+211D,U+2124,U+2190-2199,U+21A6,U+21D0-21D5,U+2200-22FF,U+2308-230B,U+27E8-27EB,U+27F5-27FF,U+1D434-1D467,U+1D6A4-1D6A5,U+1D6E2-1D71B,U+1D7D8-1D7E1"
```

The ranges cover Basic Latin, Greek, primes, the mathematical operators, common arrows,
brackets, and the mathematical italic letters that MathML uses for single-letter variables.
