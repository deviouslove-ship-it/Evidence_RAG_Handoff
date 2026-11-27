**Language / Ngôn ngữ:** [Tiếng Việt](pdf-anchor-coordinate-contract.md) · English

English counterpart of `docs/pdf-anchor-coordinate-contract.md`. The Vietnamese file is the original.

# PDF anchor coordinate contract

A valid anchor includes:

- document version ID and source hash;
- page number;
- original character offset/length;
- character boxes/quads;
- page width, height, and rotation;
- MediaBox and CropBox.

Display must use the same transform as the PDF viewer. For multiple lines, use multiple quads. Do not use one rectangle that covers too wide an area. When rotation or CropBox is uncertain, fall back to the page plus the quote, and state clearly that the highlight is not exact.

> **[Not implemented: bbox-coordinate highlighting on PDF]** The viewer currently opens the correct PDF page and displays the verbatim excerpt (`quote_exact`). Drawing a per-word highlight overlay (bbox/quads) on the PDF page, and the fixture set that proves anchor accuracy (gate WP 0.3/1.5), are decided as **not implemented**.

There is no real PDF fixture in the repo to prove anchor accuracy. The WP 0.3/1.5 gate is not implemented.
