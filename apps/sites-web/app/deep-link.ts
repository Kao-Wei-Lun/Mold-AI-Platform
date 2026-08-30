export const DEEP_LINK_VERSION = '1.0' as const;

export type DeepLinkTarget =
  | 'home'
  | 'job'
  | 'similarity'
  | 'design_review'
  | 'knowledge'
  | 'process_trial'
  | 'cae'
  | 'hmi'
  | 'rule_profile'
  | 'ingestion_batch';

export type DeepLinkContext = {
  deep_link_version: typeof DEEP_LINK_VERSION;
  target: DeepLinkTarget;
  refs: Record<string, string>;
};

export type DeepLinkErrorCode =
  | 'DEEP_LINK_VERSION_UNSUPPORTED'
  | 'DEEP_LINK_TARGET_INVALID'
  | 'DEEP_LINK_REF_INVALID';

const targetRefs: Record<DeepLinkTarget, { required: string[]; optional: string[] }> = {
  home: { required: [], optional: [] },
  job: { required: ['job_id'], optional: [] },
  similarity: { required: ['search_id'], optional: ['candidate_id'] },
  design_review: { required: ['review_id'], optional: ['finding_id'] },
  knowledge: { required: ['knowledge_search_id'], optional: ['citation_id'] },
  process_trial: { required: ['process_search_id'], optional: ['case_id'] },
  cae: { required: ['cae_comparison_id'], optional: ['metric_code'] },
  hmi: { required: ['hmi_extraction_id'], optional: [] },
  rule_profile: { required: ['profile_id'], optional: [] },
  ingestion_batch: { required: ['batch_id'], optional: [] },
};

const uuidRefs = new Set([
  'job_id',
  'search_id',
  'candidate_id',
  'review_id',
  'finding_id',
  'knowledge_search_id',
  'citation_id',
  'process_search_id',
  'case_id',
  'cae_comparison_id',
  'hmi_extraction_id',
  'profile_id',
  'batch_id',
]);

const forbiddenFields = new Set([
  'token',
  'api_key',
  'tunnel_id',
  'workspace_url',
  'return_url',
  'javascript',
  'permission',
]);

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export class DeepLinkError extends Error {
  constructor(public readonly code: DeepLinkErrorCode, message: string) {
    super(message);
    this.name = 'DeepLinkError';
  }
}

function oneValue(params: URLSearchParams, key: string): string | null {
  const values = params.getAll(key);
  if (values.length > 1) {
    throw new DeepLinkError('DEEP_LINK_REF_INVALID', `Duplicate parameter: ${key}`);
  }
  return values[0] ?? null;
}

export function parseDeepLink(input: string | URLSearchParams): DeepLinkContext {
  const params = typeof input === 'string' ? new URLSearchParams(input) : input;
  const version = oneValue(params, 'deep_link_version');
  if (version !== DEEP_LINK_VERSION) {
    throw new DeepLinkError(
      'DEEP_LINK_VERSION_UNSUPPORTED',
      'This Mold AI link uses an unsupported contract version.',
    );
  }

  const rawTarget = oneValue(params, 'target');
  if (!rawTarget || !(rawTarget in targetRefs)) {
    throw new DeepLinkError('DEEP_LINK_TARGET_INVALID', 'This Mold AI target is not supported.');
  }
  const target = rawTarget as DeepLinkTarget;
  const schema = targetRefs[target];
  const allowed = new Set(['deep_link_version', 'target', ...schema.required, ...schema.optional]);

  for (const key of params.keys()) {
    if (forbiddenFields.has(key) || !allowed.has(key)) {
      throw new DeepLinkError('DEEP_LINK_REF_INVALID', `Unexpected parameter: ${key}`);
    }
  }

  const refs: Record<string, string> = {};
  for (const key of [...schema.required, ...schema.optional]) {
    const value = oneValue(params, key);
    if (!value) {
      if (schema.required.includes(key)) {
        throw new DeepLinkError('DEEP_LINK_REF_INVALID', `Missing parameter: ${key}`);
      }
      continue;
    }
    if (value.length > 128 || /[\u0000-\u001f\u007f]/.test(value)) {
      throw new DeepLinkError('DEEP_LINK_REF_INVALID', `Invalid parameter: ${key}`);
    }
    if (uuidRefs.has(key) && !uuidPattern.test(value)) {
      throw new DeepLinkError('DEEP_LINK_REF_INVALID', `Invalid identifier: ${key}`);
    }
    refs[key] = value;
  }
  return { deep_link_version: DEEP_LINK_VERSION, target, refs };
}

export function serializeDeepLink(context: DeepLinkContext): string {
  const params = new URLSearchParams({
    deep_link_version: context.deep_link_version,
    target: context.target,
  });
  for (const key of Object.keys(context.refs).sort()) params.set(key, context.refs[key]);
  return params.toString();
}

export function deepLinkTitle(target: DeepLinkTarget): string {
  return {
    home: 'Mold AI Dashboard',
    job: 'Engineering job status',
    similarity: 'Similarity search result',
    design_review: 'Design review result',
    knowledge: 'Knowledge evidence',
    process_trial: 'Process / Trial evidence',
    cae: 'CAE comparison',
    hmi: 'HMI extraction',
    rule_profile: 'Mold rule profile',
    ingestion_batch: 'Data import job',
  }[target];
}
