import { describe, expect, it } from 'vitest';

import { DeepLinkError, parseDeepLink, serializeDeepLink } from './deep-link';

const SEARCH_ID = '11111111-1111-4111-8111-111111111111';
const CANDIDATE_ID = '22222222-2222-4222-8222-222222222222';
const PROFILE_ID = '33333333-3333-4333-8333-333333333333';
const BATCH_ID = '44444444-4444-4444-8444-444444444444';

describe('Sites deep-link contract', () => {
  it('parses and serializes an allowlisted similarity context', () => {
    const parsed = parseDeepLink(
      `deep_link_version=1.0&target=similarity&search_id=${SEARCH_ID}&candidate_id=${CANDIDATE_ID}`,
    );

    expect(parsed.target).toBe('similarity');
    expect(parsed.refs.candidate_id).toBe(CANDIDATE_ID);
    expect(serializeDeepLink(parsed)).toBe(
      `deep_link_version=1.0&target=similarity&candidate_id=${CANDIDATE_ID}&search_id=${SEARCH_ID}`,
    );
  });

  it.each([
    [`deep_link_version=1.0&target=rule_profile&profile_id=${PROFILE_ID}`, 'rule_profile', 'profile_id', PROFILE_ID],
    [`deep_link_version=1.0&target=ingestion_batch&batch_id=${BATCH_ID}`, 'ingestion_batch', 'batch_id', BATCH_ID],
  ])('supports governed record target %s', (query, target, refName, refValue) => {
    const parsed = parseDeepLink(query);
    expect(parsed.target).toBe(target);
    expect(parsed.refs[refName]).toBe(refValue);
  });

  it.each([
    'deep_link_version=2.0&target=home',
    'deep_link_version=1.0&target=unknown',
    'deep_link_version=1.0&target=job&job_id=job-1',
    `deep_link_version=1.0&target=job&job_id=${SEARCH_ID}&return_url=https://attacker.test`,
    `deep_link_version=1.0&target=job&job_id=${SEARCH_ID}&job_id=${CANDIDATE_ID}`,
    `deep_link_version=1.0&target=home&token=secret`,
  ])('rejects malformed or unsafe input: %s', (query) => {
    expect(() => parseDeepLink(query)).toThrow(DeepLinkError);
  });
});
