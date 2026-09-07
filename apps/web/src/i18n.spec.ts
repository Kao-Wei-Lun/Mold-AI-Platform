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

  it("translates every CAD similarity score lane", () => {
    setLocale("zh-TW");

    expect(translate("geometry")).toBe("幾何形狀");
    expect(translate("metadata")).toBe("產品與材料資料");
    expect(translate("topology")).toBe("拓樸結構");
    expect(translate("dimension")).toBe("外形尺寸");
    expect(translate("manufacturing")).toBe("製造特徵");
  });
});
