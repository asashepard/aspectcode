// Should trigger: test.no_assertions
describe('Test Suite', () => {
    it('should do something', () => {
        const result = calculate();
        // No assertion - test doesn't verify anything
    });
});

function calculate() {
    return 42;
}
