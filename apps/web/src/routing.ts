import type { DeepLinkTarget } from "./deepLinks";

export type WorkspaceRouteId =
  | "home"
  | "cad"
  | "similarity"
  | "design_review"
  | "knowledge"
  | "process_trial"
  | "cae"
  | "hmi"
  | "rules"
  | "master_data"
  | "mold_registry"
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
    path: "/knowledge",
    label: "Knowledge",
    group: "Governance",
    eyebrow: "Governance / Knowledge",
    title: "Search authorized engineering evidence",
    description: "Inspect claims beside citations, source authority and retrieval limitations.",
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
    label: "Master data",
    group: "Governance",
    eyebrow: "Governance / Master data",
    title: "Govern canonical engineering choices",
    description: "Manage bilingual names and lifecycle while preserving immutable engineering codes and references.",
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
  return workspaceRoutes.find((route) => route.path === normalized) || notFoundRoute;
}

const deepLinkRoutes: Record<DeepLinkTarget, WorkspaceRouteId> = {
  home: "home",
  job: "status",
  similarity: "similarity",
  design_review: "design_review",
  knowledge: "knowledge",
  process_trial: "process_trial",
  cae: "cae",
  hmi: "hmi",
};

export function routeForDeepLink(target: DeepLinkTarget): WorkspaceRoute {
  const routeId = deepLinkRoutes[target];
  return workspaceRoutes.find((route) => route.id === routeId) || workspaceRoutes[0];
}
