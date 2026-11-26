# PDF figure and table captions

Research date: 2026-11-25. Documentation/source review only; no extraction benchmark or dependency installation.

## Recommendation

Keep PDFFigures2 and retain its JSON metadata alongside the exported images. It already extracts **both figure and table captions**, including caption text and bounding boxes. A replacement library is unnecessary merely to expose those fields. Its documented scope—scholarly PDFs, especially computer science papers—also matches this corpus. [1][2]

The existing invocation uses `-m`, `-d`, and `-c`. Upstream defines these as image output prefix, JSON output prefix, and **include captions for which no figure region was found**, respectively. `-c` does not include caption pixels in the image crop. [3]

## Exact PDFFigures2 output

With `-c`, the JSON document is an object with:

- `figures`: records containing `name`, `figType` (`Figure` or `Table`), `page`, `caption`, `imageText`, `captionBoundary`, `regionBoundary`, `renderURL`, and `renderDpi` when images are saved.
- `regionless-captions`: records containing `name`, `figType`, `page`, `text`, and `boundary`; these have no corresponding extracted image.

Without `-c`, figure-data JSON is directly an array. `renderURL` gives the image filename, so it is the natural association key before image renaming. Page numbers are zero based; bounding boxes use top-left coordinates at 72 DPI. The JSON serializer preserves the case-class field names and serializes figure types as strings. [1][2][3][4]

The renderer crops `regionBoundary` and explicitly treats caption boundaries as non-figure content while cleaning crops. Therefore retaining caption **text** and rendering caption-inclusive **images** are separate changes. If caption pixels are wanted, a proposed approach is to render the union of `regionBoundary` and `captionBoundary`, scaled by `dpi / 72`; check for intervening content on actual pages. [5]

PDFFigures2 documents possible caption overrun into nearby prose, incomplete unusual captions, rotated-caption failures, and merged captions on the same line. Retaining metadata cannot recover captions the detector misses. [1]

## Alternatives if detection quality needs improvement

| Library | Verified caption API / representation | Practical implication |
|---|---|---|
| Docling | `DocumentConverter().convert(path).document`; iterate `PictureItem` and `TableItem`, then call `item.caption_text(document)`. Both use caption references; the reading-order stage links captions to pictures and tables. | Strong Python alternative with structured document output. An empty caption list produces an empty string; this is an extraction result to validate, not a completeness guarantee. The official image-export example documents page/picture image options for image crops. [6][7][8] |
| Marker | Explicit `Caption` blocks, `FigureGroup` for figures and associated captions, and `TableGroup` for tables and associated captions. | Supports both caption types in its structured representation. Group/block traversal is needed rather than assuming a flat caption field. This source review provides no evidence it will outperform the current extractor on this corpus. [9][10][11] |

Before replacing the extractor, compare detected caption text and figure/table associations on a representative paper sample, including multi-column pages and unusual captions.

## Primary sources

1. [PDFFigures2 official README: outputs, scope, known errors](https://github.com/allenai/pdffigures2/blob/master/README.md)
2. [PDFFigures2 Figure.scala: Figure, Caption, SavedFigure fields](https://github.com/allenai/pdffigures2/blob/master/src/main/scala/org/allenai/pdffigures2/Figure.scala)
3. [PDFFigures2 batch CLI: flags and JSON envelope](https://github.com/allenai/pdffigures2/blob/master/src/main/scala/org/allenai/pdffigures2/FigureExtractorBatchCli.scala)
4. [PDFFigures2 JsonProtocol.scala: serialization](https://github.com/allenai/pdffigures2/blob/master/src/main/scala/org/allenai/pdffigures2/JsonProtocol.scala)
5. [PDFFigures2 FigureRenderer.scala: rasterizeFigures](https://github.com/allenai/pdffigures2/blob/master/src/main/scala/org/allenai/pdffigures2/FigureRenderer.scala)
6. [Docling Core FloatingItem.caption_text](https://github.com/docling-project/docling-core/blob/main/docling_core/types/doc/items/node.py)
7. [Docling reading-order stage: caption attachment](https://github.com/docling-project/docling/blob/main/docling/models/stages/reading_order/readingorder_model.py)
8. [Docling official figure/table export example](https://github.com/docling-project/docling/blob/main/docs/examples/export_figures.py)
9. [Marker Caption schema](https://github.com/datalab-to/marker/blob/master/marker/schema/blocks/caption.py)
10. [Marker FigureGroup schema](https://github.com/datalab-to/marker/blob/master/marker/schema/groups/figure.py)
11. [Marker TableGroup schema](https://github.com/datalab-to/marker/blob/master/marker/schema/groups/table.py)
