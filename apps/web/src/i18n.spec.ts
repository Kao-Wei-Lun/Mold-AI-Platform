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
});
