// architecture.critical_dependency fixture
// This file is a critical dependency bottleneck - many modules depend on it
// Should trigger: architecture.critical_dependency

export class CriticalDependency {
    coreOperation(data: any): object {
        return this.process(data);
    }
    
    private process(data: any): object {
        return { result: data };
    }
}

export function criticalUtility(): CriticalDependency {
    return new CriticalDependency();
}
