// Should trigger: errors.swallowed_exception
function riskyOperation() {
    try {
        doSomething();
    } catch (e) {
        // swallowed exception
    }
}

function doSomething() {
    throw new Error("error");
}
