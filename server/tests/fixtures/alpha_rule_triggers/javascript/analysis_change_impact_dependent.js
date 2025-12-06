// Dependent file for analysis.change_impact fixture
// Depends on criticalFunction from analysis_change_impact_core

import { criticalFunction, CriticalService } from './analysis_change_impact_core';

export function useCritical() {
    return criticalFunction("data1");
}

export function useService() {
    const svc = new CriticalService();
    return svc.process("data2");
}
