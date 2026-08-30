import { fileExtension, formatFileSize, uploadPolicies, validateUploadFile } from "./fileUpload";

describe("upload file policy", () => {
  it("accepts the governed Knowledge formats including PDF and DOCX", () => {
    for (const name of ["guide.txt", "guide.MD", "guide.pdf", "guide.docx"]) {
      expect(validateUploadFile({ name, size: 1024 }, uploadPolicies.knowledge)).toBeNull();
    }
  });

  it("rejects unsupported extensions and files over each domain boundary", () => {
    expect(validateUploadFile({ name: "guide.exe", size: 1 }, uploadPolicies.knowledge))
      .toBe("unsupported_type");
    expect(validateUploadFile({ name: "part.step", size: uploadPolicies.cad.maxBytes + 1 }, uploadPolicies.cad))
      .toBe("too_large");
    expect(validateUploadFile({ name: "screen.png", size: uploadPolicies.hmi.maxBytes + 1 }, uploadPolicies.hmi))
      .toBe("too_large");
  });

  it("formats file summaries without locale-dependent output", () => {
    expect(fileExtension({ name: "part.STEP" })).toBe("step");
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(1536)).toBe("1.5 KB");
    expect(formatFileSize(2.5 * 1024 * 1024)).toBe("2.5 MB");
  });
});
