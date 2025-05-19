"""Compatibility layer for the removed cgi module.

This is a minimal replacement to make Twisted work in Python 3.13+.
"""

import html
import tempfile
import warnings
from collections import defaultdict
from urllib.parse import parse_qsl

__all__ = ["parse", "parse_multipart", "parse_header", "parse_qs",
           "parse_qsl", "escape", "FieldStorage"]

def parse(fp=None, environ=None, keep_blank_values=False, strict_parsing=False, 
          separator='&'):
    """Parse a query string given as a string argument."""
    if environ is None:
        environ = {}
    if 'QUERY_STRING' in environ:
        qs = environ['QUERY_STRING']
    elif fp is None:
        qs = ''
    else:
        qs = fp.read()
    
    from urllib.parse import parse_qs
    return parse_qs(qs, keep_blank_values, strict_parsing, encoding='utf-8',
                   errors='replace', max_num_fields=None, separator=separator)

def parse_multipart(fp, pdict, encoding='utf-8', errors='replace', 
                   boundary=None, separator='&'):
    """Parse multipart input."""
    warnings.warn("cgi.parse_multipart() is deprecated", DeprecationWarning, 
                 stacklevel=2)
    return {}

def parse_header(line):
    """Parse a Content-type header.

    Return the main content-type and a dictionary of options.
    """
    parts = [x.strip() for x in line.split(';')]
    if not parts:
        return '', {}
    
    main_value = parts[0].lower()
    result = {}
    
    for p in parts[1:]:
        if '=' in p:
            name, value = p.split('=', 1)
            name = name.strip().lower()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            result[name] = value
    return main_value, result

escape = html.escape

def parse_qs(qs, keep_blank_values=False, strict_parsing=False, encoding='utf-8',
             errors='replace', max_num_fields=None, separator='&'):
    """Parse a query string given as a string argument."""
    from urllib.parse import parse_qs as _parse_qs
    return _parse_qs(qs, keep_blank_values, strict_parsing, encoding, errors, 
                   max_num_fields, separator)

class FieldStorage:
    """Basic stub for FieldStorage class."""
    
    def __init__(self, fp=None, headers=None, outerboundary=b'',
                environ=None, keep_blank_values=False, strict_parsing=False,
                limit=None, encoding='utf-8', errors='replace', max_num_fields=None,
                separator='&'):
        self.file = None
        self.filename = None
        self.list = []
        self.type = None
        self.type_options = {}
        self.disposition = None
        self.disposition_options = {}
        self.headers = {}
        self.value = None
        
        if environ is None:
            environ = {}
        self.environ = environ
        
        if environ.get('REQUEST_METHOD', '').upper() not in ('POST', 'PUT'):
            self.list = []
            self.file = None
            return
            
        self.list = []
        self.file = None 