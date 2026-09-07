import type { CitationAnchor } from "./api/knowledge";

export type CitationOverlay = {
  left: string;
  top: string;
  width: string;
  height: string;
} | null;

export function citationOverlayStyle(anchor?: CitationAnchor): CitationOverlay {
  if (
    !anchor?.bbox_available ||
    anchor.coordinate_origin !== "top-left" ||
    anchor.coordinate_unit !== "pt" ||
    !anchor.page_size ||
    !anchor.bbox
  ) {
    return null;
  }
  const [pageWidth, pageHeight] = anchor.page_size;
  const [x0, y0, x1, y1] = anchor.bbox;
  if (
    pageWidth <= 0 ||
    pageHeight <= 0 ||
    x0 < 0 ||
    y0 < 0 ||
    x1 <= x0 ||
    y1 <= y0 ||
    x1 > pageWidth ||
    y1 > pageHeight
  ) {
    return null;
  }
  return {
    left: `${(x0 / pageWidth) * 100}%`,
    top: `${(y0 / pageHeight) * 100}%`,
    width: `${((x1 - x0) / pageWidth) * 100}%`,
    height: `${((y1 - y0) / pageHeight) * 100}%`,
  };
}
