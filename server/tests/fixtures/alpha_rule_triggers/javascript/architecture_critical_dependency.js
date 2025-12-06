// architecture.critical_dependency fixture
// This file is a critical dependency bottleneck - many modules depend on it
// Should trigger: architecture.critical_dependency

export class CriticalDependency {
    coreOperation(data) {
        return this.process(data);
    }
    
    process(data) {
        return { result: data };
    }
}

export function criticalUtility() {
    return new CriticalDependency();
}
