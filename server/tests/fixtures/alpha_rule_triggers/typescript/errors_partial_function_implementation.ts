// Should trigger: errors.partial_function_implementation
function processValue(value: number): string {
    throw new Error("not implemented");
}

class DataHandler {
    saveData(data: any): void {
        throw new Error("unimplemented");
    }
}
