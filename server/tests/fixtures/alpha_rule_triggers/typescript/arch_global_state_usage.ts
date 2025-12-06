// Should trigger: arch.global_state_usage
let globalCounter = 0;

export function increment(): number {
    globalCounter += 1;
    return globalCounter;
}
