// architecture.critical_dependency fixture - dependent 1
// Depends on the critical dependency

import { CriticalDependency, criticalUtility } from './arch_critical_dep_core';

export function consumerOne() {
    const dep = criticalUtility();
    return dep.coreOperation("from_one");
}
