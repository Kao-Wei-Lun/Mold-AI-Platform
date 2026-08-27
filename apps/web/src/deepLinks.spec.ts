import { parseDeepLink, reportDeepLinkEvent } from "./deepLinks";

const SEARCH_ID = "11111111-1111-4111-8111-111111111111";
const CANDIDATE_ID = "22222222-2222-4222-8222-222222222222";

describe("Engineering Web deep-link contract", () => {
  it("allows no deep link on normal page loads", () => {
    expect(parseDeepLink("")).toEqual({ context: null, error: null });
  });

  it("parses a canonical similarity context", () => {
    const state = parseDeepLink(
      `?deep_link_version=1.0&target=similarity&search_id=${SEARCH_ID}&candidate_id=${CANDIDATE_ID}`,
    );
    expect(state.error).toBeNull();
    expect(state.context?.target).toBe("similarity");
    expect(state.context?.refs.candidate_id).toBe(CANDIDATE_ID);
  });

  it.each([
    "?deep_link_version=2.0&target=home",
    "?deep_link_version=1.0&target=unknown",
    "?deep_link_version=1.0&target=job&job_id=job-1",
    `?deep_link_version=1.0&target=job&job_id=${SEARCH_ID}&return_url=https://attacker.test`,
    `?deep_link_version=1.0&target=job&job_id=${SEARCH_ID}&job_id=${CANDIDATE_ID}`,
    "?deep_link_version=1.0&target=home&token=secret",
  ])("rejects unsafe input: %s", (search) => {
    expect(parseDeepLink(search).error).not.toBeNull();
  });

  it("emits only safe observability metadata", () => {
    const context = parseDeepLink(`?deep_link_version=1.0&target=job&job_id=${SEARCH_ID}`).context!;
    const listener = vi.fn();
    window.addEventListener("mold-ai:deep-link-opened", listener);

    reportDeepLinkEvent("opened", context, { status: "accepted" });

    const event = listener.mock.calls[0][0] as CustomEvent;
    expect(event.detail).toMatchObject({ target: "job", status: "accepted" });
    expect(JSON.stringify(event.detail)).not.toContain(SEARCH_ID);
    expect(JSON.stringify(event.detail)).not.toContain("token");
    window.removeEventListener("mold-ai:deep-link-opened", listener);
  });
});
