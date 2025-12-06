// analysis.change_impact fixture
// This file defines a critical class used by many other files
// Should trigger: analysis.change_impact

export class CriticalService {
    process(data) {
        return this.internalProcess(data);
    }
    
    internalProcess(data) {
        return { processed: data };
    }
}

export function criticalFunction(param) {
    const service = new CriticalService();
    return service.process(param);
}
