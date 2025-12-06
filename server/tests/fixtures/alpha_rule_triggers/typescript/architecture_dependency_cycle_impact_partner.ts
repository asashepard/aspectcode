// architecture.dependency_cycle_impact fixture
// This file completes the impactful dependency cycle
// Should trigger: architecture.dependency_cycle_impact

import { cycleFunctionA } from './arch_dep_cycle_a';

export class CycleClassB {
    callA() {
        return cycleFunctionA();
    }
}

export function cycleFunctionB() {
    return new CycleClassB();
}
