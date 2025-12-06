import sys; sys.path.insert(0, '.')
from engine.validation import ValidationService
vs = ValidationService()
vs.ensure_rules_loaded()
from engine.registry import get_rule
rule = get_rule('bug.incompatible_comparison')

# Test the detection functions
print('Testing _is_numeric_literal_text:')
print(f'  5: {rule._is_numeric_literal_text("5")}')
print(f'  0: {rule._is_numeric_literal_text("0")}')

print('Testing _is_string_literal_text:')
print(f'  "5": {rule._is_string_literal_text(chr(34) + "5" + chr(34))}')

print('Testing _is_boolean_literal_text:')
print(f'  False: {rule._is_boolean_literal_text("False")}')

print('Testing _is_obviously_mismatched_literal_types:')
# 5 == "5" should be: number vs string
str_5 = chr(34) + "5" + chr(34)  # "5"
print(f'  5 vs "5": {rule._is_obviously_mismatched_literal_types("python", "==", "5", str_5)}')
# 0 == False should be: number vs boolean
print(f'  0 vs False: {rule._is_obviously_mismatched_literal_types("python", "==", "0", "False")}')
