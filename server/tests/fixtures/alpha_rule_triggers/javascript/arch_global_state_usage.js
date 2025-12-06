// Should trigger: arch.global_state_usage
let globalCounter = 0;

function increment() {
    globalCounter += 1;
    return globalCounter;
}
