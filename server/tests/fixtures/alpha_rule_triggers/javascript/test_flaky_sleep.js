// Should trigger: test.flaky_sleep
describe('Flaky Test', () => {
    it('should wait', async () => {
        startProcess();
        await new Promise(r => setTimeout(r, 5000));  // flaky sleep
        expect(checkResult()).toBe(true);
    });
});

function startProcess() {}
function checkResult() { return true; }
