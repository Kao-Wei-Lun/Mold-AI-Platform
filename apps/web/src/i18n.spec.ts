import { setLocale, translate } from "./i18n";

describe("i18n", () => {
  afterEach(() => setLocale("en"));

  it("uses English as a direct fallback and translates Traditional Chinese parameters", () => {
    setLocale("en");
    expect(translate("Open {title}", { title: "CAD" })).toBe("Open CAD");

    setLocale("zh-TW");
    expect(translate("Open {title}", { title: "CAD" })).toBe("開啟CAD");
    expect(document.documentElement.lang).toBe("zh-TW");
    expect(window.localStorage.getItem("mold-ai.locale")).toBe("zh-TW");
  });

  it("preserves unknown governed source text instead of inventing a translation", () => {
    setLocale("zh-TW");
    expect(translate("Company rule source text")).toBe("Company rule source text");
  });

  it("translates geometry ranking limitations and block labels", () => {
    setLocale("zh-TW");
    expect(translate("Scores express ranking relevance, not the probability that a mold can be reused."))
      .toBe("分數代表排序相關度，不代表模具可以沿用的機率。");
    expect(translate("Public CAD geometry ranking has not yet passed independent human-labelled evaluation."))
      .toBe("公開 CAD 幾何排序尚未通過獨立人工標記資料的品質驗收。");
    expect(translate("principal_extent_ratios")).toBe("主軸外形比例");
    expect(translate("How geometry was ranked")).toBe("幾何排序的評分依據");
  });

  it("translates every CAD similarity score lane", () => {
    setLocale("zh-TW");

    expect(translate("geometry")).toBe("幾何形狀");
    expect(translate("metadata")).toBe("產品與材料資料");
    expect(translate("topology")).toBe("拓樸結構");
    expect(translate("dimension")).toBe("外形尺寸");
    expect(translate("manufacturing")).toBe("製造特徵");
  });
});
