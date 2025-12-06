// Part of imports.cycle.advanced fixture - this file imports imports_cycle_advanced back
// Should trigger: imports.cycle.advanced

import { functionA } from './imports_cycle_advanced';

export function functionB() {
    return functionA() + " from B";
}
