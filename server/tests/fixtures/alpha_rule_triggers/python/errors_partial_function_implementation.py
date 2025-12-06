# Should trigger: errors.partial_function_implementation
def process_value(value):
    raise NotImplementedError("This function is not implemented yet")

class DataHandler:
    def save_data(self, data):
        raise NotImplementedError()
