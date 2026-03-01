import os
import sys

def fix_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # اكتشاف نمط المسافات: أول سطر له مسافات بادئة
    indent_char = None
    spaces_per_level = 4
    for line in lines:
        if line.strip() and line[0] in ' \t':
            n = len(line) - len(line.lstrip())
            if n > 0:
                indent_char = line[0]
                if n == 1 or (indent_char == ' ' and n < 4):
                    spaces_per_level = 4
                else:
                    spaces_per_level = 4
                break

    result = []
    require_next_indent = None

    for line in lines:
        content = line.rstrip('\n\r')
        if not content.strip():
            result.append('\n')
            require_next_indent = None
            continue

        stripped = content.lstrip()
        n_old = len(content) - len(stripped)
        if indent_char and n_old > 0:
            level = n_old if (indent_char == ' ' and n_old <= 4) else n_old // 4
            new_indent = level * 4
        else:
            new_indent = n_old * 4 if n_old <= 4 else n_old

        if require_next_indent is not None and not stripped.startswith('#'):
            if new_indent <= require_next_indent - 4:
                new_indent = require_next_indent
            require_next_indent = None

        if content.rstrip().endswith(':'):
            require_next_indent = new_indent + 4

        result.append(' ' * new_indent + stripped + '\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(result)
    print('تم إصلاح:', path)


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    handlers_dir = os.path.join(base, 'handlers')
    for name in ['common.py', 'calc.py']:
        path = os.path.join(handlers_dir, name)
        if os.path.isfile(path):
            fix_file(path)
    print('انتهى.')
