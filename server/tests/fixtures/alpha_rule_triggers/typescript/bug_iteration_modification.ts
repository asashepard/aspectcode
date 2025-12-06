// Should trigger: bug.iteration_modification
function removeEvens(numbers: number[]): number[] {
    for (const num of numbers) {
        if (num % 2 === 0) {
            const idx = numbers.indexOf(num);
            numbers.splice(idx, 1);  // modifying array during iteration
        }
    }
    return numbers;
}
