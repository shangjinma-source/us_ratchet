"""Fill Artifact Tool's missing native hyperlink capability, without cell edits.

Only the full navigation workbook is supported. Input/output are bytes; the
publisher remains responsible for source authentication and create-only IO.
OOXML semantics: learn.microsoft.com/dotnet/api/documentformat.openxml.spreadsheet.hyperlink
"""
import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PACKAGE = 'http://schemas.openxmlformats.org/package/2006/relationships'


def require(value, message):
    if not value:
        raise ValueError(message)


def add_native_navigation_links(workbook_bytes, links):
    require(type(workbook_bytes) is bytes and type(links) is list and len(links) == 1632, 'Complete navigation inputs')
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as source:
        names = source.namelist()
        require(len(names) == len(set(names)), 'Duplicate ZIP entries')
        require(not any(name.startswith('_xmlsignatures/') for name in names), 'Signed input is not supported')
        book = ET.fromstring(source.read('xl/workbook.xml'))
        book_rel = ET.fromstring(source.read('xl/_rels/workbook.xml.rels'))
        sheets = [node for node in book.findall(f'{{{MAIN}}}sheets/{{{MAIN}}}sheet') if node.get('name') == '全部任务']
        require(len(sheets) == 1, 'Unique full task sheet')
        identifier = sheets[0].get(f'{{{REL}}}id')
        targets = [node for node in book_rel if node.get('Id') == identifier]
        require(len(targets) == 1 and targets[0].get('TargetMode') != 'External' and targets[0].get('Type') == REL + '/worksheet', 'Internal worksheet relationship')
        target = targets[0].get('Target')
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl', target))
        require(re.fullmatch(r'xl/worksheets/sheet\d+\.xml', path), 'Bounded worksheet part')
        sheet = ET.fromstring(source.read(path))
        require(sheet.tag == f'{{{MAIN}}}worksheet', 'Worksheet root')
        require(sheet.find(f'{{{MAIN}}}hyperlinks') is None, 'Create-only hyperlink addition')
        cell_nodes = sheet.findall(f'.//{{{MAIN}}}c')
        cells = {node.get('r'): node for node in cell_nodes}
        require(len(cells) == len(cell_nodes), 'Duplicate cell addresses')
        relationship_path = posixpath.join(posixpath.dirname(path), '_rels', posixpath.basename(path) + '.rels')
        relationships = ET.fromstring(source.read(relationship_path)) if relationship_path in names else ET.Element(f'{{{PACKAGE}}}Relationships')
        existing_ids = {node.get('Id') for node in relationships}
        require(len(existing_ids) == len(relationships), 'Unique existing relationship IDs')
        hyperlink_nodes = ET.Element(f'{{{MAIN}}}hyperlinks')
        for ordinal, link in enumerate(links):
            require(type(link) is dict and set(link) == {'worksheet', 'cell', 'target', 'location'}, 'Exact native link intent')
            require(link['worksheet'] == '全部任务' and link['cell'] == f'H{ordinal + 2}', 'Full ordered task link cells')
            require(type(link['target']) is str and re.fullmatch(r'package-\d{4}\.xlsx', link['target']), 'Relative package target only')
            require(type(link['location']) is str and re.fullmatch(r"'任务索引'!A[1-9]\d*", link['location']), 'Explicit task index destination')
            cell = cells.get(link['cell'])
            require(cell is not None and cell.find(f'{{{MAIN}}}f') is None, 'Existing literal filename cell')
            value = cell.find(f'{{{MAIN}}}v')
            require(cell.get('t') == 'str' and value is not None and value.text == link['target'], 'Link target equals saved display filename')
            local_cell = cells.get(f'I{ordinal + 2}')
            require(local_cell is not None and local_cell.find(f'{{{MAIN}}}f') is None and local_cell.get('t') in (None, 'n'), 'Saved local task number')
            local_value = local_cell.find(f'{{{MAIN}}}v')
            require(local_value is not None and re.fullmatch(r'[1-9]\d*', local_value.text or ''), 'Exact positive local task number')
            require(link['location'] == "'任务索引'!A" + str(int(local_value.text) + 1), 'Link row equals displayed local task number')
            link_id = f'navTaskLink{ordinal + 1}'
            require(link_id not in existing_ids, 'No relationship ID collision')
            ET.SubElement(relationships, f'{{{PACKAGE}}}Relationship', {'Id': link_id, 'Type': REL + '/hyperlink', 'Target': link['target'], 'TargetMode': 'External'})
            ET.SubElement(hyperlink_nodes, f'{{{MAIN}}}hyperlink', {'ref': link['cell'], f'{{{REL}}}id': link_id, 'location': link['location']})
        # CT_Worksheet order: hyperlinks follow validations and precede print/drawings.
        later = {'printOptions', 'pageMargins', 'pageSetup', 'headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'oleObjects', 'controls', 'webPublishItems', 'tableParts', 'extLst'}
        position = next((i for i, node in enumerate(sheet) if node.tag.rsplit('}', 1)[-1] in later), len(sheet))
        sheet.insert(position, hyperlink_nodes)
        changed = {path: ET.tostring(sheet, encoding='utf-8', xml_declaration=True), relationship_path: ET.tostring(relationships, encoding='utf-8', xml_declaration=True)}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as destination:
            for info in source.infolist():
                destination.writestr(info, changed.pop(info.filename, source.read(info.filename)))
            for name, data in changed.items():
                destination.writestr(name, data)
        return output.getvalue()
