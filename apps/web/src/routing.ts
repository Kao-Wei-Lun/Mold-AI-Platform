import type { DeepLinkContext, DeepLinkTarget } from "./deepLinks";

export type WorkspaceRouteId =
  | "home"
  | "cad"
  | "mold_planning"
  | "similarity"
  | "design_review"
  | "knowledge_search"
  | "knowledge"
  | "process_trial"
  | "cae"
  | "hmi"
  | "rules"
  | "master_data"
  | "mold_registry"
  | "engineering_data"
  | "history_data"
  | "identity"
  | "status"
  | "not_found";

export type WorkspaceRoute = {
  id: WorkspaceRouteId;
  path: string;
  label: string;
  group: "Overview" | "Engineering" | "Governance";
  eyebrow: string;
  title: string;
  description: string;
};

export const workspaceRoutes: WorkspaceRoute[] = [
  {
    id: "home",
    path: "/",
    label: "Demo guide",
    group: "Overview",
    eyebrow: "Guided engineering demo",
    title: "From CAD evidence to an engineering decision",
    description:
      "Follow a governed workflow, or open one focused workspace without loading every capability at once.",
  },
  {
    id: "cad",
    path: "/engineering/cad",
    label: "CAD & artifacts",
    group: "Engineering",
    eyebrow: "Engineering / CAD",
    title: "Prepare a versioned geometry context",
    description: "Upload or select governed Demo geometry before starting downstream analysis.",
  },
  {
    id: "mold_planning",
    path: "/engineering/mold-planning",
    label: "Mold planning",
    group: "Engineering",
    eyebrow: "Engineering / Mold planning",
    title: "Resolve the right standard before design review",
    description: "Build a governed engineering context, understand the selected standard and preserve a traceable planning decision.",
  },
  {
    id: "similarity",
    path: "/engineering/similarity",
    label: "Similarity",
    group: "Engineering",
    eyebrow: "Engineering / Similarity",
    title: "Rank comparable molds with explainable evidence",
    description: "Keep the query context fixed while inspecting candidates, scores and limitations.",
  },
  {
    id: "design_review",
    path: "/engineering/design-review",
    label: "Design review",
    group: "Engineering",
    eyebrow: "Engineering / Design review",
    title: "Evaluate deterministic mold rules",
    description: "Separate immutable findings from reviewer decisions and model explanations.",
  },
  {
    id: "knowledge_search",
    path: "/engineering/knowledge-search",
    label: "Engineering knowledge search",
    group: "Engineering",
    eyebrow: "Engineering / Knowledge search",
    title: "Find governed engineering knowledge",
    description: "Ask engineering questions and inspect authorized excerpts, citations and retrieval limitations.",
  },
  {
    id: "process_trial",
    path: "/engineering/process-trial",
    label: "Process / trial",
    group: "Engineering",
    eyebrow: "Engineering / Process and trial",
    title: "Compare governed trial evidence",
    description: "Explore historical parameters and controlled trial candidates without machine write-back.",
  },
  {
    id: "cae",
    path: "/engineering/cae",
    label: "CAE / Moldflow",
    group: "Engineering",
    eyebrow: "Engineering / CAE",
    title: "Compare compatible simulation runs",
    description: "Review structured metrics only after solver, mesh, material and unit compatibility passes.",
  },
  {
    id: "hmi",
    path: "/engineering/hmi",
    label: "HMI → Excel",
    group: "Engineering",
    eyebrow: "Engineering / Machine HMI",
    title: "Review extracted machine settings before export",
    description: "Keep image evidence, normalized values, human corrections and spreadsheet lineage together.",
  },
  {
    id: "knowledge",
    path: "/governance/knowledge",
    label: "Knowledge document management",
    group: "Governance",
    eyebrow: "Governance / Knowledge documents",
    title: "Manage governed knowledge documents",
    description: "Import, inspect, review, publish and retire the sources used by engineering knowledge search.",
  },
  {
    id: "rules",
    path: "/governance/rules",
    label: "Mold rules",
    group: "Governance",
    eyebrow: "Governance / Mold rules",
    title: "Understand the rules that govern design review",
    description: "Browse the approved profile, versioned thresholds, ownership and source references.",
  },
  {
    id: "mold_registry",
    path: "/governance/mold-registry",
    label: "Mold registry",
    group: "Governance",
    eyebrow: "Governance / Mold registry",
    title: "Govern molds, revisions and CAD relationships",
    description: "Keep project, part, mold, revision and artifact lineage in one controlled hierarchy.",
  },
  {
    id: "engineering_data",
    path: "/governance/engineering-data",
    label: "Engineering data",
    group: "Governance",
    eyebrow: "Governance / Operational evidence",
    title: "Govern trial, CAE and HMI evidence",
    description: "Manage controlled lifecycles, corrections, versions and lineage without overwriting source evidence.",
  },
  {
    id: "history_data",
    path: "/data/overview",
    label: "Data library",
    group: "Governance",
    eyebrow: "Governance / Data library",
    title: "Browse governed engineering data",
    description: "Open complete records, versions, relationships, lineage and audit evidence without overwriting history.",
  },
  {
    id: "identity",
    path: "/governance/identity",
    label: "Accounts & access",
    group: "Governance",
    eyebrow: "Governance / Identity and access",
    title: "Manage individual accounts and governed access",
    description: "Control local Demo identities, roles, data scopes and active sessions with audit evidence.",
  },
  {
    id: "master_data",
    path: "/governance/master-data",
    label: "Engineering reference data",
    group: "Governance",
    eyebrow: "Governance / Engineering reference data",
    title: "Engineering reference data and choices",
    description: "Manage mold types and shared engineering choices while preserving immutable codes, lifecycle and references.",
  },
  {
    id: "status",
    path: "/status",
    label: "Demo status",
    group: "Governance",
    eyebrow: "Operations / Demo status",
    title: "Verify the platform before a demonstration",
    description: "See dependency readiness and the current private access boundary in one place.",
  },
];

const notFoundRoute: WorkspaceRoute = {
  id: "not_found",
  path: "/not-found",
  label: "Not found",
  group: "Overview",
  eyebrow: "Navigation error",
  title: "This workspace page does not exist",
  description: "Use the navigation to return to a supported Mold AI workflow.",
};

export function resolveWorkspaceRoute(pathname: string): WorkspaceRoute {
  const normalized = pathname !== "/" ? pathname.replace(/\/+$/, "") : pathname;
  if (normalized === "/knowledge") {
    return workspaceRoutes.find((route) => route.id === "knowledge") || notFoundRoute;
  }
  if (normalized === "/data" || normalized.startsWith("/data/")) {
    return workspaceRoutes.find((route) => route.id === "history_data") || notFoundRoute;
  }
  if (normalized.startsWith("/governance/mold-registry/")) {
    const segments = normalized.split("/").filter(Boolean);
    const validKinds = new Set(["projects", "parts", "molds", "revisions"]);
    if (segments.length === 4 && validKinds.has(segments[2]) && segments[3]) {
      return workspaceRoutes.find((route) => route.id === "mold_registry") || notFoundRoute;
    }
    return notFoundRoute;
  }
  return workspaceRoutes.find((route) => route.path === normalized) || notFoundRoute;
}

const deepLinkRoutes: Record<DeepLinkTarget, WorkspaceRouteId> = {
  home: "home",
  job: "status",
  similarity: "similarity",
  design_review: "design_review",
  knowledge: "knowledge_search",
  process_trial: "process_trial",
  cae: "cae",
  hmi: "hmi",
  rule_profile: "rules",
  mold_plan: "mold_planning",
  ingestion_batch: "history_data",
};

export function routeForDeepLink(target: DeepLinkTarget): WorkspaceRoute {
  const routeId = deepLinkRoutes[target];
  return workspaceRoutes.find((route) => route.id === routeId) || workspaceRoutes[0];
}

export function pathForDeepLink(context: DeepLinkContext): string {
  if (context.target === "ingestion_batch") {
    return `/data/imports/${context.refs.batch_id}`;
  }
  return routeForDeepLink(context.target).path;
}
