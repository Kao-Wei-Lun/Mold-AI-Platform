import { pathForDeepLink, resolveWorkspaceRoute, routeForDeepLink } from "./routing";

describe("Engineering Workspace routes", () => {
  it("resolves canonical paths and trailing slashes", () => {
    expect(resolveWorkspaceRoute("/engineering/cad").id).toBe("cad");
    expect(resolveWorkspaceRoute("/governance/rules/").id).toBe("rules");
    expect(resolveWorkspaceRoute("/governance/identity").id).toBe("identity");
    expect(resolveWorkspaceRoute("/governance/mold-registry").id).toBe("mold_registry");
    expect(resolveWorkspaceRoute("/governance/engineering-data").id).toBe("engineering_data");
    expect(resolveWorkspaceRoute("/data/overview").id).toBe("history_data");
    expect(resolveWorkspaceRoute("/data/trials/trial-1").id).toBe("history_data");
    expect(resolveWorkspaceRoute("/missing").id).toBe("not_found");
  });

  it.each([
    ["similarity", "/engineering/similarity"],
    ["design_review", "/engineering/design-review"],
    ["knowledge", "/knowledge"],
    ["process_trial", "/engineering/process-trial"],
    ["cae", "/engineering/cae"],
    ["hmi", "/engineering/hmi"],
    ["job", "/status"],
    ["rule_profile", "/governance/rules"],
    ["ingestion_batch", "/data/overview"],
  ] as const)("maps %s deep links to %s", (target, path) => {
    expect(routeForDeepLink(target).path).toBe(path);
  });

  it("maps an ingestion deep link to the exact import batch detail path", () => {
    const batchId = "44444444-4444-4444-8444-444444444444";
    expect(pathForDeepLink({
      deep_link_version: "1.0",
      target: "ingestion_batch",
      refs: { batch_id: batchId },
      correlation_id: "correlation-1",
    })).toBe(`/data/imports/${batchId}`);
  });
});
