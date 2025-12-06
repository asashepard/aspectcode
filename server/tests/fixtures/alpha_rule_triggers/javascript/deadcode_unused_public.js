// deadcode.unused_public fixture
// This file defines public symbols that are never used externally
// Should trigger: deadcode.unused_public

export class UnusedPublicClass {
    unusedMethod() {
        return "never called";
    }
}

export function unusedPublicFunction() {
    return "dead code";
}

export const PUBLIC_UNUSED_CONSTANT = "never referenced";

// This is internal and is fine
function privateHelper() {
    return "internal";
}
