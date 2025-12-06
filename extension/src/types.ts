export type Span = { 
  start: { line: number; column: number }; 
  end: { line: number; column: number } 
};

export type Finding = {
  id: string; 
  code: string; 
  severity: "info" | "warn" | "error";
  file: string; 
  span: Span; 
  message: string; 
  fixable: boolean; 
  suggested_patchlet?: string;
  selected?: boolean;
};

export type IndexStats = { 
  snapshotId: string; 
  fileCount: number; 
  bytes: number; 
  tookMs: number 
};

export type ValidateStats = { 
  total: number; 
  fixable: number; 
  byCode: Record<string, number>; 
  tookMs: number 
};

// Graph/Data
export type GraphSummary = {
  snapshotId: string;
  computedAtMs: number;
  topIn: Array<{ file: string; in: number }>;
  topOut: Array<{ file: string; out: number }>;
  // reserved for future: cycles, modules, function nodes, etc.
};

// Settings for Aspect Code configuration
export type AspectCodeSettings = {
  ignore_patterns?: string[];
  disabled_rules?: string[];
  thresholds?: Record<string, number>;
};

// Panel view model
export type PanelState = {
  snapshot?: IndexStats;
  lastValidate?: ValidateStats;
  findings?: Finding[];
  busy?: boolean;
  error?: string;
  history: Array<{ ts: number; kind: string; meta?: any }>;
  graph?: GraphSummary;
  config?: AspectCodeSettings;
  ui?: { 
    activeTab?: "overview"|"graph"|"settings";
    expandedSections?: {
      overview: boolean;
      graph: boolean;
      settings: boolean;
    };
  };
};