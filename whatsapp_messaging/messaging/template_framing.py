"""Optional fixed text framing shared by local and Meta messages."""
import re


def validate(header=None, footer=None):
    values = []
    for label, value in (('Header', header), ('Footer', footer)):
        value = value or ''
        if not isinstance(value, str) or len(value) > 60:
            raise ValueError(f'{label} must be text up to 60 characters.')
        if '{{' in value or '}}' in value or re.search(r'[\r\n\t\x00-\x1f]', value):
            raise ValueError(f'{label} must be one line of fixed text. Put personalized fields in Message Text instead.')
        values.append(value)
    return tuple(values)


def texts(components):
    header = next((c.get('text', '') for c in components if c.get('type') == 'HEADER'), '')
    footer = next((c.get('text', '') for c in components if c.get('type') == 'FOOTER'), '')
    return header, footer


def document_header(components):
    return any(c.get('type') == 'HEADER' and c.get('format') == 'DOCUMENT' for c in components)


def compose(body, header=None, footer=None):
    header, footer = validate(header, footer)
    return '\n\n'.join(value for value in (header, body, footer) if value)


def supported(components):
    if not isinstance(components, list) or any(not isinstance(c, dict) for c in components):
        return False
    kinds = [c.get('type') for c in components]
    if kinds.count('BODY') != 1 or kinds.count('HEADER') > 1 or kinds.count('FOOTER') > 1:
        return False
    if any(kind not in ('HEADER', 'BODY', 'FOOTER') for kind in kinds):
        return False
    if any(c.get('type') == 'HEADER' and c.get('format') not in ('TEXT', 'DOCUMENT') for c in components):
        return False
    try:
        validate(*texts(components))
    except ValueError:
        return False
    return all(c.get('text', '').strip() or (c.get('type') == 'HEADER' and c.get('format') == 'DOCUMENT') for c in components)
