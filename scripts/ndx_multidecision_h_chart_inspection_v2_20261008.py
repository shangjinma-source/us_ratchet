"""Independent OOXML chart-to-cell checks; no builder or spreadsheet SDK."""
from pathlib import PurePosixPath
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
RID = '{' + NS['r'] + '}id'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relationships(archive, member):
    path = PurePosixPath(member)
    location = str(path.parent / '_rels' / (path.name + '.rels'))
    if location not in archive.namelist():
        return {}
    result = {}
    for entry in ET.fromstring(archive.read(location)):
        require(entry.attrib.get('TargetMode') != 'External', 'No external chart relationship')
        key = entry.attrib['Id']
        require(key not in result, 'Unique relationship id')
        target = entry.attrib['Target']
        resolved = target.lstrip('/') if target.startswith('/') else posixpath.normpath(str(path.parent / target))
        require(not resolved.startswith('../') and resolved in archive.namelist(), 'Physical internal relationship')
        result[key] = resolved
    return result


def column(number):
    result = ''
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def range_parts(formula):
    match = re.fullmatch(r"(?:'((?:[^']|'')+)'|([^'!]+))!\$?([A-Z]+)\$?([1-9][0-9]*):\$?([A-Z]+)\$?([1-9][0-9]*)", formula)
    require(match is not None, 'Explicit rectangular chart source range')
    sheet = match[1].replace("''", "'") if match[1] is not None else match[2]
    def col(label):
        n = 0
        for ch in label: n = n * 26 + ord(ch) - 64
        return n
    left, top, right, bottom = col(match[3]), int(match[4]), col(match[5]), int(match[6])
    require(left <= right and top <= bottom and (left == right or top == bottom), 'One-dimensional chart source')
    return sheet, [column(c) + str(r) for r in range(top, bottom + 1) for c in range(left, right + 1)]


def inspect_chart_parts(path, expected_charts):
    checked_points = 0
    with zipfile.ZipFile(path) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'No duplicate archive members')
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(element.itertext()) for element in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        bookrels = relationships(archive, 'xl/workbook.xml')
        sheet_members = {sheet.attrib['name']: bookrels[sheet.attrib[RID]] for sheet in book.findall('s:sheets/s:sheet', NS)}
        cells, found = {}, []
        for name, member in sheet_members.items():
            root = ET.fromstring(archive.read(member)); values = {}
            for cell in root.findall('s:sheetData/s:row/s:c', NS):
                require(cell.find('s:f', NS) is None, 'Chart source must remain saved literals')
                key = cell.attrib['r'];require(key not in values, 'Unique source cell')
                kind = cell.attrib.get('t');value = cell.find('s:v', NS)
                if kind == 's':
                    require(value is not None and value.text is not None and value.text.isdigit(), 'Shared string index')
                    index = int(value.text);require(index < len(shared), 'Bounded shared string index');parsed = shared[index]
                elif kind == 'inlineStr': parsed = ''.join(cell.find('s:is', NS).itertext())
                elif kind == 'str': parsed = None if value is None else value.text
                elif value is None or value.text is None: parsed = None
                elif kind == 'b':
                    require(value.text in ('0', '1'), 'Exact boolean XML');parsed = value.text == '1'
                else:
                    require(kind in (None, 'n'), 'Numeric chart source only');parsed = float(value.text)
                values[key] = parsed
            cells[name] = values
            sheetrels = relationships(archive, member)
            for drawing in root.findall('s:drawing', NS):
                drawing_member = sheetrels[drawing.attrib[RID]]
                drawingrels = relationships(archive, drawing_member)
                for chart in ET.fromstring(archive.read(drawing_member)).findall('.//c:chart', NS):
                    found.append((name, drawingrels[chart.attrib[RID]]))
        require(len(found) == len(expected_charts), 'Complete chart count')
        require(len({member for _, member in found}) == len(found), 'No duplicate linked chart')
        physical = {member for member in archive.namelist() if re.fullmatch(r'xl/(?:drawings/)?charts/[^/]+\.xml', member)}
        if '[Content_Types].xml' in archive.namelist():
            physical.update(item.attrib['PartName'].lstrip('/') for item in ET.fromstring(archive.read('[Content_Types].xml'))
                            if item.attrib.get('ContentType') == 'application/vnd.openxmlformats-officedocument.drawingml.chart+xml')
        require(physical == {member for _, member in found}, 'No unlinked extra chart')

        def read_range(formula):
            sheet, addresses = range_parts(formula)
            require(sheet in cells, 'Chart source sheet exists')
            return [cells[sheet].get(address) for address in addresses]

        for (sheet, member), expected in zip(found, expected_charts):
            require(sheet == expected['sheet_name'], 'Chart remains on registered view')
            root = ET.fromstring(archive.read(member))
            title = ''.join(item.text or '' for item in root.findall('.//c:chart/c:title//a:t', NS))
            require(title == expected['title'], 'Exact chart title')
            series = root.findall('.//c:lineChart/c:ser', NS)
            require(len(series) == len(expected['series']) == len(root.findall('.//c:ser', NS)), 'Registered line series only')
            for actual, wanted in zip(series, expected['series']):
                name = actual.find('c:tx/c:v', NS)
                require(actual.find('c:tx/c:strRef', NS) is None, 'Registered builder uses literal series identity, not cached name references')
                require(name is not None and name.text == wanted['name'], 'Exact series identity')
                for category, tag, formula_key, value_key in ((True, 'c:cat', 'categories_formula', 'categories'),
                                                            (False, 'c:val', 'values_formula', 'values')):
                    node = actual.find(tag, NS)
                    require(node is not None, 'Series axis data')
                    formula = node.find('.//c:f', NS)
                    require(formula is not None and range_parts(formula.text) == range_parts(wanted[formula_key]), 'Exact curve source formula')
                    values = read_range(formula.text)
                    types_match = all(type(v) is str for v in values) if category else all(type(v) in (int, float) for v in values)
                    require(values == wanted[value_key] and types_match, 'Complete original chart data')
                    for cache in list(node.findall('.//c:strCache', NS)) + list(node.findall('.//c:numCache', NS)):
                        points = cache.findall('c:pt', NS);count = cache.find('c:ptCount', NS)
                        # The SDK emits empty caches for linked ranges. Resolve
                        # the whole registered range above; never accept a
                        # partial/nonempty cache as a substitute for those cells.
                        if count is not None and count.attrib['val'] == '0' and not points:
                            continue
                        require(count is not None and count.attrib['val'] == str(len(values)) and len(points) == len(values), 'Full chart cache count')
                        require([p.attrib['idx'] for p in points] == list(map(str, range(len(values)))), 'Chart cache original point order')
                        cached = [p.find('c:v', NS).text for p in points]
                        if not category: cached = list(map(float, cached))
                        require(cached == values, 'Chart cache agrees with literal cells')
                    checked_points += len(values)
    return dict(status='PASS_ALL_CHART_SOURCE_CELLS', chart_count=len(expected_charts), checked_axis_points=checked_points,
                financial_recomputation_performed=False, missing_paths_filled_with_zero=False)
