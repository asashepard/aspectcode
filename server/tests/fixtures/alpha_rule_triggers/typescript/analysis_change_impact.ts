// analysis.change_impact fixture
// This file defines a critical class used by many other files
// Should trigger: analysis.change_impact

export class CriticalService {
    process(data: any): object {
        return this.internalProcess(data);
    }
    
    private internalProcess(data: any): object {
        return { processed: data };
    }
}

export function criticalFunction(param: any): object {
    const service = new CriticalService();
    return service.process(param);
}
