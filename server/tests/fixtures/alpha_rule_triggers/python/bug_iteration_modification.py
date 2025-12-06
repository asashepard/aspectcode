# Should trigger: bug.iteration_modification
def remove_evens(numbers):
    for num in numbers:
        if num % 2 == 0:
            numbers.remove(num)  # modifying list during iteration
    return numbers
