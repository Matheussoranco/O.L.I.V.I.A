import sys

content = open('src/olivia/study/solver.py', 'r', encoding='utf-8').read()

old = '''    iterable = (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE", "integrate", "Integrate"),
    )
    for pattern, op, verb in iterable:
        match = pattern.search(text)
        if match:'''

new = '''    iterable = (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE", "integrate", "Integrate"),
    )
    print(f"RUNTIME: iterable = {iterable}", file=sys.stderr)
    print(f"RUNTIME: len = {len(iterable)}", file=sys.stderr)
    for pattern, op, verb in iterable:
        match = pattern.search(text)
        if match:'''

# Simple approach - just remove all debug prints
content = open('src/olivia/study/solver.py', 'r', encoding='utf-8').read()
content = content.replace(
    '''    iterable = (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE", "integrate", "Integrate"),
    )
    for pattern, op, verb in iterable:
        print(f"RUNTIME: iterable = {iterable}", file=sys.stderr)
        print(f"RUNTIME: len = {len(iterable)}", file=sys.stderr)
        match = pattern.search(text)
        if match:''',
    '''    for pattern, op, verb in (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE", "integrate", "Integrate"),
    ):
        match = pattern.search(text)
        if match:''')

open('src/olivia/study/solver.py', 'w', encoding='utf-8').write(content)
print('Cleaned up')