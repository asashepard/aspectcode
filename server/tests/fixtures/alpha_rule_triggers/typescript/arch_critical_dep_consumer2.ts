// architecture.critical_dependency fixture - dependent 2
// Depends on the critical dependency

import { CriticalDependency, criticalUtility } from './arch_critical_dep_core';

export function consumerTwo(): object {
    const dep = new CriticalDependency();
    return dep.coreOperation("from_two");
}
