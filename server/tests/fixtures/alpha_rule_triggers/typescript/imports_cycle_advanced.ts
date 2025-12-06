// Part of imports.cycle.advanced fixture - this file imports imports_cycle_advanced_b
// Should trigger: imports.cycle.advanced

import { functionB } from './imports_cycle_advanced_b';

export function functionA(): string {
    return functionB() + " from A";
}
