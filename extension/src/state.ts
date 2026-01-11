import * as vscode from "vscode";

// --- INFERRED TYPES ---
// (Based on your extension.ts file)

type Finding = {
  id: string;
  code: string;
  severity: "info" | "warn" | "error";
  file: string;
  message: string;
  fixable: boolean;
  selected: boolean;
  span?: {
    start: { line: number; column: number };
    end: { line: number; column: number };
  };
  _raw: any;
};

type SnapshotStats = {
  snapshotId: string;
  fileCount: number;
  bytes: number;
  tookMs: number;
};

type ValidateStats = {
  total: number;
  fixable: number;
  byCode: Record<string, number>;
  tookMs: number;
};

type HistoryItem = {
  ts: number;
  kind: "index" | "reindex" | "validate" | "autofix";
  meta: Record<string, any>;
};

type PanelUIState = {
  activeTab: string;
  lastValidationFiles?: string[]; // Track files validated in last smart validation
  autoValidationEnabled?: boolean; // Track if auto-validation is enabled
};

type FixCapability = { 
  rule: string; 
  patchlet: string; 
};

type Capabilities = { 
  language: 'python'; 
  fixable_rules: FixCapability[]; 
};

// --- PANEL STATE DEFINITION ---

/**
 * Defines the complete in-memory state of the panel.
 */
export type PanelState = {
  // --- Ephemeral State ---
  // (Reset on every load)
  busy: boolean;
  error?: string;
  findings: Finding[];
  lastValidate?: ValidateStats;
  dependencyGraphCache?: Map<string, any>; // Cache for dependency graph data

  // --- Persistent State ---
  // (Saved and reloaded)
  snapshot?: SnapshotStats;
  history: HistoryItem[];
  ui: PanelUIState;
  capabilities?: Capabilities;
};

/**
 * The default state for a new session.
 */
const DEFAULT_STATE: PanelState = {
  // Ephemeral fields are reset
  busy: false,
  error: undefined,
  findings: [],
  lastValidate: undefined,
  dependencyGraphCache: new Map<string, any>(),

  // Persistent fields have defaults
  snapshot: undefined,
  history: [],
  ui: { 
    activeTab: "overview",
    lastValidationFiles: [],
    autoValidationEnabled: true
  },
  capabilities: undefined,
};

/**
 * Keys from PanelState that we want to save to globalState.
 * EVERYTHING ELSE will be reset on load.
 */
const PERSISTENT_KEYS: (keyof PanelState)[] = ["snapshot", "history", "ui", "capabilities"];

// --- STATE MANAGER CLASS ---

export { FixCapability, Capabilities };

export class AspectCodeState {
  private _state: PanelState;
  private readonly storageKey = "aspectcode.panel.v1";

  readonly _onDidChange = new vscode.EventEmitter<PanelState>();
  readonly onDidChange = this._onDidChange.event;

  constructor(private ctx: vscode.ExtensionContext) {
    // Initialize with default state. load() will be called by activate()
    this._state = DEFAULT_STATE;
  }

  /**
   * Returns the current in-memory state.
   */
  get s() {
    return this._state;
  }

  /**
   * Loads the persistent state from storage and merges it with the
   * default state to ensure all ephemeral fields are reset.
   */
  load() {
    // 1. Load the *saved* (and incomplete) state from storage
    const persistentState = this.ctx.globalState.get<Partial<PanelState>>(
      this.storageKey,
      {}
    );

    // 2. Create the new in-memory state
    this._state = {
      ...DEFAULT_STATE,   // Start with defaults (busy: false, findings: [], etc.)
      ...persistentState, // Merge in saved data (history, snapshot, ui)
    };

    // 3. (Optional) Force-clear ephemeral fields just in case
    this._state.busy = false;
    this._state.error = undefined;
    this._state.findings = [];
    this._state.lastValidate = undefined;


    // 4. Notify listeners of the clean state
    this._onDidChange.fire(this._state);
  }

  /**
   * Updates the in-memory state, saves the persistent parts,
   * and notifies listeners.
   */
  update(patch: Partial<PanelState>) {
    // 1. Update the in-memory state
    this._state = { ...this._state, ...patch };

    // 2. Save the persistent parts to storage
    this.savePersistentState();

    // 3. Notify listeners
    this._onDidChange.fire(this._state);
  }

  /**
   * Returns the capabilities data if available.
   */
  getCapabilities(): Capabilities | undefined {
    return this._state.capabilities;
  }

  /**
   * Returns a set of safe rule codes that can be auto-fixed.
   */
  getSafeRuleSet(): Set<string> {
    const capabilities = this._state.capabilities;
    if (!capabilities) return new Set();
    
    return new Set(capabilities.fixable_rules.map(r => r.rule));
  }

  /**
   * Updates capabilities and saves to persistent state.
   */
  setCapabilities(capabilities: Capabilities) {
    this.update({ capabilities });
  }

  /**
   * (Internal) Creates an object with *only* the persistent keys
   * and saves it to globalState.
   */
  private savePersistentState() {
    const stateToPersist: Partial<PanelState> = {};

    for (const key of PERSISTENT_KEYS) {
      if (this._state[key] !== undefined) {
        (stateToPersist as any)[key] = this._state[key];
      }
    }

    // This now only saves { snapshot, history, ui, capabilities }
    this.ctx.globalState.update(this.storageKey, stateToPersist);
  }
}