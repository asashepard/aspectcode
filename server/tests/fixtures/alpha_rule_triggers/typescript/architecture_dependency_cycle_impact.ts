// architecture.dependency_cycle_impact fixture
// This file is part of an impactful dependency cycle
// Should trigger: architecture.dependency_cycle_impact

import { cycleFunctionB } from './arch_dep_cycle_b';

export class CycleClassA {
    callB() {
        return cycleFunctionB();
    }
}

export function cycleFunctionA() {
    return new CycleClassA();
}
