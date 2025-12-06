// deadcode.unused_public fixture
// This file defines public symbols that are never used externally
// Should trigger: deadcode.unused_public

export class UnusedPublicClass {
    unusedMethod(): string {
        return "never called";
    }
}

export function unusedPublicFunction(): string {
    return "dead code";
}

export const PUBLIC_UNUSED_CONSTANT: string = "never referenced";

// This is internal and is fine
function privateHelper(): string {
    return "internal";
}
