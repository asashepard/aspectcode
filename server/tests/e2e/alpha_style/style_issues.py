"""
Alpha Style Test Project

This file contains intentional style issues that should be caught
by alpha style rules:
- style.mixed_indentation
- style.trailing_whitespace
- style.missing_newline_eof
"""

# style.mixed_indentation - Mixed tabs and spaces
class MixedIndentationExample:
    def __init__(self):
        self.data = {}   
	self.count = 0  # This line uses tab instead of spaces
    
    def process(self):
        for item in self.data:
            if item:   
		print(item)  # Tab instead of spaces
            else:
                print("empty")   

# style.trailing_whitespace - Lines with trailing spaces
def trailing_whitespace_example():  
    result = "test"    
    
    if result:   
        print("found")  
    else:  
        print("not found")   
    
    return result    


# More mixed indentation
def complex_function():
    x = 1
	if x > 0:  # Tab here
        y = 2
	    if y > 1:  # Tab here  
            z = 3
		print(f"z = {z}")  # Tab here
    
    return x + y + z


class StyleIssues:
    """Class with various style problems"""
    
    def __init__(self):  
        self.items = []   
        
    def add_item(self, item):   
        self.items.append(item)  
        
    def process_items(self):  
        for item in self.items:   
            if item:  
		result = self.transform(item)  # Tab indentation
                print(result)   
            else:
	            print("skipping empty item")  # Tab indentation
                
    def transform(self, item):  
        return item.upper()   


# Function with trailing spaces throughout
def messy_formatting():   
    data = {   
        "name": "test",   
        "value": 42   
    }   
    
    for key in data:   
        value = data[key]   
        
        if isinstance(value, str):   
            print(f"String: {value}")   
        elif isinstance(value, int):   
            print(f"Number: {value}")   
        else:   
            print(f"Other: {value}")   
    
    return data   


# Mix of tabs and spaces in function
def tab_space_mix():
    x = 1
	y = 2  # Tab
    z = 3
	result = x + y + z  # Tab  
    return result


# Nested mixed indentation
def nested_mixed():
    for i in range(3):
        if i % 2 == 0:   
	    print(f"Even: {i}")  # Tab
        else:
            print(f"Odd: {i}")   
            
        for j in range(2):   
	        if j == 0:  # Tab
                print(f"  First: {j}")   
	        else:  # Tab  
                print(f"  Second: {j}")   


# Comprehensive style issues function
def all_style_issues():   
    items = ["a", "b", "c"]   
    
    for item in items:   
	if item:  # Tab
            result = item.upper()   
	    print(result)  # Tab with trailing space
        
    return items   


if __name__ == "__main__":   
    trailing_whitespace_example()   
    complex_function()   
    messy_formatting()   