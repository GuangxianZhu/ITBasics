#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_tool.py - cut large C/C++ code into pieces an AI chat (e.g. Microsoft 365 Copilot) can read.

Run without arguments for an interactive menu (that is what run_code_tool.bat does).
The folder this is run from is the "root"; results go to <root>/_ai_out/.

Commands:
  index                            function index of all C/C++ files     -> code_index.txt
  func NAME [NAME ...]             extract whole functions by name        -> extract_func.txt
  grep WORD [WORD ...] [-c N] [-f] [-i]
                                   extract keyword hits with N lines of
                                   context (-f: the whole function)       -> extract_grep.txt
  merge PATH [PATH ...]            merge files / folders into one txt     -> merged_files.txt
  (dragging files onto run_code_tool.bat = merge)

Standard library only, Python 3.6+.
The C/C++ parser is a heuristic (no compiler): for #if/#ifdef ... #else it reads the first
branch and skips #if 0. A few definitions in unusual code may be missed.
"""

import argparse
import bisect
import datetime
import os
import re
import sys
import time

# ---------------------------------------------------------------- settings (edit freely)

CODE_EXTS = {'.c', '.cc', '.cpp', '.cxx', '.c++', '.h', '.hh', '.hpp', '.hxx', '.h++', '.inl', '.ipp'}
EXCLUDE_DIRS = {'.git', '.svn', '.hg', '.vs', '.idea', '.vscode', 'node_modules', '__pycache__', 'ipch', '_ai_out'}
ENCODINGS = ('utf-8', 'cp932')        # tried in order; Shift-JIS source is cp932
OUT_DIR_NAME = '_ai_out'
DEFAULT_CONTEXT = 15                  # lines before/after a keyword hit
LONG_OUTPUT_WARN = 3000               # warn when an output is longer than this many lines
BIG_FILE_WARN = 5000                  # merge: warn for files longer than this

# ---------------------------------------------------------------- file helpers


def read_text(path):
    """Return (text with '\\n' line ends, encoding name, size in bytes)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data.startswith(b'\xef\xbb\xbf'):
        text, enc = data[3:].decode('utf-8', 'replace'), 'utf-8'
    elif data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text, enc = data.decode('utf-16', 'replace'), 'utf-16'
    else:
        text = None
        for enc in ENCODINGS:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        if text is None:
            enc = ENCODINGS[-1] + '(?)'
            text = data.decode(ENCODINGS[-1], 'replace')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text, enc, len(data)


def is_binary(path):
    with open(path, 'rb') as f:
        head = f.read(4096)
    if head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return False
    return b'\x00' in head


def find_code_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in CODE_EXTS:
                out.append(os.path.join(dirpath, name))
    return out


def rel(path, root):
    try:
        r = os.path.relpath(path, root)
    except ValueError:            # different drive on Windows
        return path.replace('\\', '/')
    if r.startswith('..'):
        return os.path.abspath(path).replace('\\', '/')
    return r.replace('\\', '/')


def human_size(n):
    if n >= 1 << 20:
        return '%.1f MB' % (n / float(1 << 20))
    if n >= 1 << 10:
        return '%.1f KB' % (n / float(1 << 10))
    return '%d B' % n


def write_output(root, name, lines):
    out_dir = os.path.join(root, OUT_DIR_NAME)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, name)
    # UTF-8 with BOM + CRLF: Notepad and Copilot both read it correctly
    with open(path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def header_lines(title, root, extra=()):
    lines = ['# ' + title,
             '# Root: ' + os.path.abspath(root),
             '# Generated: ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    lines += ['# ' + e for e in extra]
    return lines


def numbered(src_lines, start, end, width, marks=()):
    """Lines start..end (1-based, inclusive) as '  123 | code'; lines in marks get '>'."""
    out = []
    for n in range(start, end + 1):
        flag = '>' if n in marks else ' '
        out.append('%s%*d | %s' % (flag, width, n, src_lines[n - 1]))
    return out


# ---------------------------------------------------------------- C/C++ parsing

_TOKEN_RE = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)


def _blank_token(m):
    t = m.group()
    nl = '\n' * t.count('\n')
    if t[0] == '"':
        return '""' + nl
    if t[0] == "'":
        return "''" + nl
    return ' ' + nl


def _is_zero(expr):
    return re.match(r'^\(?\s*0\s*\)?\s*$', expr) is not None


def _strip_preprocessor(s):
    """Blank directive lines; keep only the first branch of #if/#else (skip #if 0)."""
    out = []
    stack = []          # [parent_active, branch_taken]
    active = True
    cont = False
    for line in s.split('\n'):
        if cont:
            cont = line.rstrip().endswith('\\')
            out.append('')
            continue
        st = line.lstrip()
        if st.startswith('#'):
            cont = line.rstrip().endswith('\\')
            m = re.match(r'#\s*(\w+)(.*)', st)
            if m:
                kw, rest = m.group(1), m.group(2).strip()
                if kw in ('if', 'ifdef', 'ifndef'):
                    zero = kw == 'if' and _is_zero(rest)
                    stack.append([active, not zero])
                    active = active and not zero
                elif kw == 'elif' and stack:
                    parent, taken = stack[-1]
                    if taken:
                        active = False
                    else:
                        zero = _is_zero(rest)
                        active = parent and not zero
                        stack[-1][1] = not zero
                elif kw == 'else' and stack:
                    parent, taken = stack[-1]
                    active = parent and not taken
                    stack[-1][1] = True
                elif kw == 'endif' and stack:
                    active = stack.pop()[0]
            out.append('')
            continue
        out.append(line if active else '')
    return '\n'.join(out)


_ACCESS_RE = re.compile(r'\b(?:(?:public|private|protected)(?:\s+(?:slots|Q_SLOTS))?|signals|Q_SIGNALS)\s*:(?!:)')
_TAIL_RE = re.compile(r'\s*(?:\b(?:const|volatile|override|final|noexcept|mutable|try)'
                      r'|\b(?:throw|noexcept|__attribute__)\s*\((?:[^()]|\([^()]*\))*\)'
                      r'|&&|&|->[^(){};]*)\s*$')
_NAME_RE = re.compile(r'((?:[A-Za-z_]\w*\s*(?:<[^<>;{}]*>)?\s*::\s*)*~?\s*'
                      r'(?:operator\s*\(\s*\)|operator\b[^();{}]*|[A-Za-z_]\w*))\s*$')
_KIND_RE = re.compile(r'\b(namespace|class|struct|union|enum)\b')
_CTRL = {'if', 'for', 'while', 'switch', 'catch', 'return', 'sizeof', 'do', 'else', 'case',
         'defined', 'alignof', 'decltype', 'static_assert', 'new', 'delete'}
_SKIP_TOKENS = {'class', 'struct', 'union', 'enum', 'typedef', 'template', 'typename', 'final',
                'static', 'extern', 'const', 'volatile', 'alignas', '__declspec', 'dllexport', 'dllimport'}


def _has_top_level_eq(s):
    depth = 0
    for i, ch in enumerate(s):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth = max(0, depth - 1)
        elif ch == '=' and depth == 0:
            prev = s[i - 1] if i else ''
            nxt = s[i + 1] if i + 1 < len(s) else ''
            if prev in '=!<>' or nxt == '=':
                continue
            if re.search(r'operator\s*\W{0,2}$', s[max(0, i - 12):i]):
                continue
            return True
    return False


def _cut_ctor_init(s):
    """Cut a constructor initializer list: 'A::A(int x) : m(x)' -> 'A::A(int x) '."""
    depth = 0
    last = ''
    for i, ch in enumerate(s):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth = max(0, depth - 1)
        elif ch == ':' and depth == 0:
            nxt = s[i + 1] if i + 1 < len(s) else ''
            prev = s[i - 1] if i else ''
            if nxt != ':' and prev != ':' and last == ')':
                return s[:i]
        if not ch.isspace():
            last = ch
    return s


def _match_open(s, close_idx):
    depth = 0
    for i in range(close_idx, -1, -1):
        if s[i] == ')':
            depth += 1
        elif s[i] == '(':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _norm(s):
    return ' '.join(s.split())


def classify(h):
    """Classify the text in front of a '{'.

    Returns (kind, name, start_offset, signature); kind is 'func', 'other' (skip the block),
    a container kind ('class', 'struct', 'union', 'enum', 'namespace') or 'block'.
    """
    off = 0
    for m in _ACCESS_RE.finditer(h):
        off = m.end()
    body = h[off:]
    lead = len(body) - len(body.lstrip())
    body = body.lstrip()
    off += lead
    if not body:
        return 'block', '', off, ''
    if _has_top_level_eq(body):
        return 'other', '', off, ''

    s_cut = _cut_ctor_init(body)
    s2 = s_cut.rstrip()
    while True:
        t = _TAIL_RE.sub('', s2)
        if t == s2:
            break
        s2 = t.rstrip()

    if s2.endswith(')'):
        op = _match_open(s2, len(s2) - 1)
        if op <= 0:
            return 'other', '', off, ''
        prefix = s2[:op]
        win = max(0, len(prefix) - 300)
        m = _NAME_RE.search(prefix, win)
        if not m:
            return 'other', '', off, ''
        name = re.sub(r'\s*::\s*', '::', _norm(m.group(1)))
        name = re.sub(r'~\s+', '~', name)
        if name.split('::')[-1] in _CTRL:
            return 'other', '', off, ''
        # skip macro calls in front of the signature, e.g. IMPLEMENT_DYNAMIC(A, B)
        start = 0
        depth = 0
        for i in range(m.start(1)):
            ch = prefix[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth = max(0, depth - 1)
                if depth == 0:
                    start = i + 1
        while start < len(prefix) and prefix[start].isspace():
            start += 1
        sig = _norm(body[start:len(s_cut)])
        if len(sig) > 200:
            sig = sig[:197] + '...'
        return 'func', name, off + start, sig

    m = _KIND_RE.search(body)
    if m:
        kind = m.group(1)
        after = body[m.end():]
        if kind == 'namespace':
            t = re.match(r'\s*([\w:]+)', after)
            return 'namespace', t.group(1) if t else '(anonymous)', off, ''
        head = re.split(r'(?<!:):(?!:)', after, maxsplit=1)[0]
        toks = [t for t in re.findall(r'[A-Za-z_]\w*', head) if t not in _SKIP_TOKENS]
        return kind, toks[-1] if toks else '(anonymous)', off, ''
    if re.match(r'extern\s*""\s*$', body) or '(' not in body:
        return 'block', '', off, ''
    return 'other', '', off, ''


_QUALIFY_KINDS = ('class', 'struct', 'union')


def parse_cpp(text):
    """Find definitions. Returns (records, warning or None).

    record: dict(kind, name, sig, start, end) with 1-based line numbers.
    """
    s = _TOKEN_RE.sub(_blank_token, text)
    s = _strip_preprocessor(s)
    line_starts = [0] + [m.end() for m in re.finditer(r'\n', s)]

    def lineno(pos):
        return bisect.bisect_right(line_starts, pos)

    nonws = re.compile(r'\S')
    records = []
    stack = []            # dicts: type ('func'/'other'/container kind), name, rec
    boundary = 0
    skip = 0              # brace depth inside a function / skipped block
    stray = 0
    for m in re.finditer(r'[{};]', s):
        c = m.group()
        p = m.start()
        if skip:
            if c == '{':
                skip += 1
            elif c == '}':
                skip -= 1
                if skip == 0:
                    top = stack.pop()
                    if top['rec'] is not None:
                        top['rec']['end'] = lineno(p)
                    boundary = p + 1
            continue
        if c == ';':
            boundary = p + 1
            continue
        if c == '}':
            if stack:
                top = stack.pop()
                if top['rec'] is not None:
                    top['rec']['end'] = lineno(p)
            else:
                stray += 1
            boundary = p + 1
            continue
        # '{'
        hm = nonws.search(s, boundary, p)
        hstart = hm.start() if hm else p
        if p - hstart > 3000:
            hstart = p - 3000
        kind, name, off, sig = classify(s[hstart:p])
        if kind == 'func':
            if '::' not in name:
                owners = [x['name'] for x in stack if x['type'] in _QUALIFY_KINDS]
                if owners:
                    name = '::'.join(owners + [name])
            rec = {'kind': 'func', 'name': name, 'sig': sig, 'start': lineno(hstart + off), 'end': None}
            records.append(rec)
            stack.append({'type': 'func', 'name': name, 'rec': rec})
            skip = 1
        elif kind == 'other':
            stack.append({'type': 'other', 'name': '', 'rec': None})
            skip = 1
        else:
            rec = None
            if kind != 'block':
                rec = {'kind': kind, 'name': name, 'sig': '', 'start': lineno(hstart + off), 'end': None}
                records.append(rec)
            stack.append({'type': kind, 'name': name, 'rec': rec})
        boundary = p + 1

    last_line = len(line_starts)
    for x in stack:
        if x['rec'] is not None and x['rec']['end'] is None:
            x['rec']['end'] = last_line
    warning = None
    if stack or stray:
        warning = 'braces do not balance (unusual macros / #ifdef?) - this file may be incomplete'
    records.sort(key=lambda r: (r['start'], -r['end']))
    return records, warning


def enclosing_func(records, line):
    best = None
    for r in records:
        if r['kind'] == 'func' and r['start'] <= line <= r['end']:
            if best is None or r['start'] >= best['start']:
                best = r
    return best


# ---------------------------------------------------------------- commands


def cmd_index(root):
    t0 = time.time()
    files = find_code_files(root)
    if not files:
        print('No C/C++ files found under ' + root)
        return None
    summary, detail = [], []
    total_lines = total_funcs = 0
    for path in files:
        rp = rel(path, root)
        text, enc, size = read_text(path)
        n_lines = text.count('\n') + 1
        recs, warn = parse_cpp(text)
        funcs = [r for r in recs if r['kind'] == 'func']
        total_lines += n_lines
        total_funcs += len(funcs)
        summary.append('%s  | %d lines | %s | %d functions | %s%s'
                       % (rp, n_lines, human_size(size), len(funcs), enc, '  | !' if warn else ''))
        detail.append('')
        detail.append('## %s  (%d lines, %s)' % (rp, n_lines, human_size(size)))
        if warn:
            detail.append('! ' + warn)
        if not recs:
            detail.append('(no definitions found)')
        w = len(str(n_lines))
        for r in recs:
            span = 'L%*d-%-*d' % (w, r['start'], w, r['end'])
            if r['kind'] == 'func':
                sig = r['sig'] or r['name']
                if '::' in r['name'] and r['name'] not in sig.replace(' ', ''):
                    sig += '   (%s)' % r['name']
                detail.append('%s  func   %s  [%d lines]' % (span, sig, r['end'] - r['start'] + 1))
            else:
                detail.append('%s  %-6s %s' % (span, r['kind'], r['name']))
        print('  indexed %s (%d functions)' % (rp, len(funcs)))
    lines = header_lines('C/C++ function index', root, [
        'Files: %d, lines: %d, functions: %d' % (len(files), total_lines, total_funcs),
        'Format: L<start>-<end>  <kind>  <signature>  [<length>]. Line numbers are 1-based.',
        'Heuristic parser: first branch of #if/#ifdef is used, #if 0 is skipped; a few definitions may be missed.'])
    lines += ['', '## File summary'] + summary + detail
    out = write_output(root, 'code_index.txt', lines)
    print('\nDone in %.1f s: %s' % (time.time() - t0, out))
    print('%d files, %d functions, index is %d lines' % (len(files), total_funcs, len(lines)))
    return out


def _func_matches(rec_name, query):
    if rec_name == query or rec_name.endswith('::' + query):
        return True
    return rec_name.split('::')[-1] == query


def cmd_func(root, names):
    names = [n.strip() for n in names if n.strip()]
    if not names:
        print('No function name given.')
        return None
    files = find_code_files(root)
    bases = [n.split('::')[-1] for n in names]
    found = {n: [] for n in names}      # name -> [(path, rec, src_lines)]
    loose = {n: [] for n in names}
    for path in files:
        text, _, _ = read_text(path)
        if not any(b in text for b in bases):
            continue
        recs, _ = parse_cpp(text)
        src = text.split('\n')
        for r in recs:
            if r['kind'] != 'func':
                continue
            for n in names:
                if _func_matches(r['name'], n):
                    found[n].append((path, r, src))
                elif n.lower() in r['name'].lower():
                    loose[n].append((path, r, src))
    body, notes = [], []
    total = 0
    seen = set()
    for n in names:
        hits = found[n]
        if not hits and loose[n]:
            hits = loose[n]
            notes.append('"%s": no exact match, using %d partial match(es)' % (n, len(hits)))
        if not hits:
            notes.append('"%s": not found' % n)
            continue
        for path, r, src in hits:
            key = (path, r['start'])
            if key in seen:
                continue
            seen.add(key)
            rp = rel(path, root)
            body.append('')
            body.append('===== FILE: %s  FUNC: %s  L%d-L%d =====' % (rp, r['name'], r['start'], r['end']))
            body += numbered(src, r['start'], r['end'], len(str(len(src))))
            total += r['end'] - r['start'] + 1
            print('  %s  %s  L%d-L%d (%d lines)' % (rp, r['name'], r['start'], r['end'], r['end'] - r['start'] + 1))
    for note in notes:
        print('  ' + note)
    if not body:
        print('Nothing extracted.')
        return None
    lines = header_lines('Extracted functions', root, [
        'Query: ' + ', '.join(names),
        'Format: each block starts with "===== FILE: <path>  FUNC: <name>  L<start>-L<end> =====";',
        '        every line is "<original line number> | <code>".'] + notes)
    lines += body
    out = write_output(root, 'extract_func.txt', lines)
    print('\nDone: %s  (%d code lines)' % (out, total))
    if len(lines) > LONG_OUTPUT_WARN:
        print('Note: output is long (%d lines); the AI may not read all of it.' % len(lines))
    return out


def _merge_ranges(ranges):
    ranges.sort()
    out = []
    for a, b in ranges:
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def cmd_grep(root, words, context=DEFAULT_CONTEXT, whole_func=False, ignore_case=False):
    words = [w for w in words if w]
    if not words:
        print('No keyword given.')
        return None
    files = find_code_files(root)
    keys = [w.lower() for w in words] if ignore_case else words
    body, summary = [], []
    total_hits = 0
    for path in files:
        text, _, _ = read_text(path)
        hay = text.lower() if ignore_case else text
        if not any(k in hay for k in keys):
            continue
        src = text.split('\n')
        hits = []
        for i, line in enumerate(src, 1):
            l2 = line.lower() if ignore_case else line
            if any(k in l2 for k in keys):
                hits.append(i)
        if not hits:
            continue
        total_hits += len(hits)
        rp = rel(path, root)
        recs, _ = parse_cpp(text)
        width = len(str(len(src)))
        marks = set(hits)
        blocks = []          # (start, end, label)
        if whole_func:
            funcs, loose = {}, []
            for h in hits:
                f = enclosing_func(recs, h)
                if f is None:
                    loose.append([max(1, h - 5), min(len(src), h + 5)])
                else:
                    funcs[(f['start'], f['end'])] = f
            for (a, b), f in funcs.items():
                blocks.append((a, b, 'FUNC: %s' % f['name']))
            for a, b in _merge_ranges(loose):
                blocks.append((a, b, 'outside functions'))
        else:
            for a, b in _merge_ranges([[max(1, h - context), min(len(src), h + context)] for h in hits]):
                names = []
                for h in hits:
                    if a <= h <= b:
                        f = enclosing_func(recs, h)
                        nm = f['name'] if f else '(outside functions)'
                        if nm not in names:
                            names.append(nm)
                blocks.append((a, b, 'in: ' + ', '.join(names)))
        blocks.sort()
        n_out = 0
        for a, b, label in blocks:
            body.append('')
            body.append('===== FILE: %s  L%d-L%d  %s =====' % (rp, a, b, label))
            body += numbered(src, a, b, width, marks)
            n_out += b - a + 1
        summary.append('%s: %d hit line(s), %d block(s)' % (rp, len(hits), len(blocks)))
        print('  %s: %d hit line(s)' % (rp, len(hits)))
    if not body:
        print('No hits for: ' + ' / '.join(words))
        return None
    mode = 'whole enclosing function' if whole_func else '%d lines before/after each hit' % context
    lines = header_lines('Keyword extract', root, [
        'Keywords: %s  (%s, %s)' % (' / '.join(words), 'ignore case' if ignore_case else 'case sensitive', mode),
        'Format: each block starts with "===== FILE: <path>  L<start>-L<end>  <function> =====";',
        '        every line is "<original line number> | <code>"; lines containing a keyword start with ">".'])
    lines += ['', '## Hits per file'] + summary + body
    out = write_output(root, 'extract_grep.txt', lines)
    print('\nDone: %s  (%d hit lines, output %d lines)' % (out, total_hits, len(lines)))
    if len(lines) > LONG_OUTPUT_WARN:
        print('Note: output is long; the AI may not read all of it. Use more specific keywords or less context.')
    return out


def cmd_merge(root, paths):
    files = []
    for p in paths:
        p = p.strip().strip('"')
        if os.path.isdir(p):
            files += find_code_files(p)
        elif os.path.isfile(p):
            files.append(p)
        else:
            print('  not found: ' + p)
    seen, uniq = set(), []
    for f in files:
        k = os.path.abspath(f).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    body, listing = [], []
    total = 0
    for f in uniq:
        rp = rel(f, root)
        if is_binary(f):
            print('  skipped (binary): ' + rp)
            continue
        text, _, _ = read_text(f)
        src = text.split('\n')
        if src and src[-1] == '':
            src.pop()
        if len(src) > BIG_FILE_WARN:
            print('  note: %s has %d lines - consider index + func/grep instead' % (rp, len(src)))
        listing.append('%s  (%d lines)' % (rp, len(src)))
        body.append('')
        body.append('===== FILE: %s  (%d lines) =====' % (rp, len(src)))
        body += numbered(src, 1, len(src), len(str(max(1, len(src)))))
        total += len(src)
        print('  added %s (%d lines)' % (rp, len(src)))
    if not body:
        print('Nothing to merge.')
        return None
    lines = header_lines('Merged files', root, [
        'Files: %d, lines: %d' % (len(listing), total),
        'Format: each file starts with "===== FILE: <path> ====="; every line is "<line number> | <code>".'])
    lines += ['', '## Files'] + listing + body
    out = write_output(root, 'merged_files.txt', lines)
    print('\nDone: %s  (%d files, %d lines)' % (out, len(listing), total))
    if len(lines) > LONG_OUTPUT_WARN:
        print('Note: output is long; the AI may not read all of it.')
    return out


# ---------------------------------------------------------------- menu / CLI

MENU = """
=============================================
 Code tool for AI      root: {root}
=============================================
 1  Function index            -> _ai_out\\code_index.txt
 2  Extract functions by name -> _ai_out\\extract_func.txt
 3  Extract by keyword        -> _ai_out\\extract_grep.txt
 4  Merge files: drag files / folders onto run_code_tool.bat
 0  Exit
"""


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return '0'


def menu(root):
    while True:
        print(MENU.format(root=root))
        c = ask('Select: ').strip()
        if c in ('0', 'q'):
            return
        if not c:
            continue
        try:
            if c == '1':
                cmd_index(root)
            elif c == '2':
                names = ask('Function names (space separated, e.g. FillStart CTank::CheckLevel): ').split()
                cmd_func(root, names)
            elif c == '3':
                words = ask('Keywords (space separated, any of them matches): ').split()
                if not words:
                    continue
                ctx = ask('Context lines before/after [Enter = %d, f = whole function]: ' % DEFAULT_CONTEXT).strip().lower()
                ic = ask('Ignore upper/lower case? [y/N]: ').strip().lower() == 'y'
                if ctx == 'f':
                    cmd_grep(root, words, whole_func=True, ignore_case=ic)
                else:
                    n = int(ctx) if ctx.isdigit() else DEFAULT_CONTEXT
                    cmd_grep(root, words, context=n, ignore_case=ic)
            elif c == '4':
                print('Close this window, then drag files or folders onto run_code_tool.bat.')
            else:
                print('Unknown choice.')
        except Exception as e:          # keep the menu alive
            print('Error: %r' % e)


def main(argv):
    root = os.getcwd()
    if not argv:
        menu(root)
        return 0
    cmds = ('index', 'func', 'grep', 'merge')
    if argv[0] not in cmds:              # files dragged onto the .bat
        cmd_merge(root, argv)
        return 0
    ap = argparse.ArgumentParser(prog='code_tool.py')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('index')
    p = sub.add_parser('func')
    p.add_argument('names', nargs='+')
    p = sub.add_parser('grep')
    p.add_argument('words', nargs='+')
    p.add_argument('-c', '--context', type=int, default=DEFAULT_CONTEXT)
    p.add_argument('-f', '--function', action='store_true', help='output the whole enclosing function')
    p.add_argument('-i', '--ignore-case', action='store_true')
    p = sub.add_parser('merge')
    p.add_argument('paths', nargs='+')
    a = ap.parse_args(argv)
    if a.cmd == 'index':
        cmd_index(root)
    elif a.cmd == 'func':
        cmd_func(root, a.names)
    elif a.cmd == 'grep':
        cmd_grep(root, a.words, a.context, a.function, a.ignore_case)
    elif a.cmd == 'merge':
        cmd_merge(root, a.paths)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
