// Should trigger: errors.partial_function_implementation
function processValue(value) {
    throw new Error("not implemented");
}

class DataHandler {
    saveData(data) {
        throw new Error("unimplemented");
    }
}
