import { citationOverlayStyle } from "./pdfCitation";

describe("citationOverlayStyle", () => {
  it("maps a validated top-left PDF bbox to percentages", () => {
    expect(citationOverlayStyle({
      page_no: 2,
      page_size: [600, 800],
      bbox: [60, 80, 300, 240],
      bbox_available: true,
      bbox_precision: "exact",
      coordinate_origin: "top-left",
      coordinate_unit: "pt",
      page_rotation: 0,
    })).toEqual({ left: "10%", top: "10%", width: "40%", height: "20%" });
  });

  it("refuses unavailable or out-of-page coordinates", () => {
    expect(citationOverlayStyle(undefined)).toBeNull();
    expect(citationOverlayStyle({
      page_no: 1,
      page_size: [600, 800],
      bbox: [590, 10, 610, 30],
      bbox_available: true,
      bbox_precision: "estimated",
      coordinate_origin: "top-left",
      coordinate_unit: "pt",
      page_rotation: 0,
    })).toBeNull();
  });
});
