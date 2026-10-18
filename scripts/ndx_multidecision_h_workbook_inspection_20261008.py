"""Independent OOXML cell-by-cell readback; no spreadsheet builder calls."""
from pathlib import PurePosixPath
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
SUBTITLE = '仅投影已审原值；精确数值按文本保存。无拟合、无风险重算、无晋级结论。'


def expected_sheets(payload):
    result = [('阅读说明', ['项目','说明'], [
        ['交付范围','11张已存比较表与6张原持仓补充表；不是完整H。'],
        ['数值口径','原字符串逐字保留；不转浮点、不四舍五入、不作图表近似。'],
        ['缺失口径','480日候选连续风险原本未保存；8条阻断轨道未执行。'],
        ['阅读方法','先读身份、日期、状态及原值；右侧JSON和来源列仅用于核对。'],
        ['原证据限制','原表中的历史阶段缺口说明保持原文；本工作簿不改变其历史含义。'],
        ['派生风险','未提供：不填零、不借用其他账户风险。']])]
    chunks=[]
    for table in payload['tables']:
        indexes = [i for i, h in enumerate(table['headers']) if not ('JSON' in h or '来源' in h)]
        indexes += [i for i, h in enumerate(table['headers']) if 'JSON' in h or '来源' in h]
        rows=[]
        for r,row in enumerate(table['rows'],1):
            values=[]
            for i in indexes:
                value=row[i]
                if isinstance(value,str) and len(value.encode('utf-16-le'))//2>32767:
                    count=(len(value)+13999)//14000
                    for part in range(count):chunks.append([table['name'],r,i+1,part+1,count,value[part*14000:(part+1)*14000]])
                    value=f'原长文本分块｜{table["name"]}｜数据行{r}｜原列{i+1}｜分块{count}'
                values.append(value)
            rows.append(values)
        result.append((table['name'], [table['headers'][i] for i in indexes], rows))
    result.append(('派生风险未提供',['状态','范围','说明'],[['未提供','候选连续账户480日','本版本未消费派生风险证据；不将缺失风险写成0。'],['未提供','新链聚合','需另行固定来源、口径及独立审计后接入。']]))
    result.append(('原长文本分块',['原表','数据行','原列','分块序号','总分块','原文本分块JSON'],chunks))
    return result


def address(row, col):
    name = ''
    while col:
        col, digit = divmod(col - 1, 26);name = chr(65 + digit) + name
    return name + str(row)


def inspect_workbook(path, payload):
    expected = expected_sheets(payload);checked = 0;row_counts = []
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != len(set(z.namelist())): raise ValueError('Duplicate ZIP entries')
        if any('externalLink' in n or n.endswith('vbaProject.bin') for n in z.namelist()): raise ValueError('External or executable workbook')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        relations = {x.attrib['Id']: x.attrib['Target'] for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        actual = ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS)
        if [x.attrib['name'] for x in actual] != [x[0] for x in expected]: raise ValueError('Exact sheet order and inventory')
        physical = {n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)}
        consumed = set()
        for sheet, (name, headers, rows) in zip(actual, expected):
            target = relations[sheet.attrib[R]]
            member = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
            if '..' in PurePosixPath(member).parts or member not in physical: raise ValueError('Exact worksheet part')
            consumed.add(member);root = ET.fromstring(z.read(member));values = {}
            for cell in root.findall('s:sheetData/s:row/s:c', NS):
                loc = cell.attrib['r']
                if loc in values or cell.find('s:f', NS) is not None: raise ValueError('Duplicate cell or formula')
                kind = cell.attrib.get('t');v = cell.find('s:v', NS)
                if kind == 's': value = shared[int(v.text)]
                elif kind == 'inlineStr': value = ''.join(cell.find('s:is', NS).itertext())
                elif kind == 'b':
                    if v is None or v.text not in ('0','1'): raise ValueError('Invalid XML boolean')
                    value = v.text == '1'
                elif v is None or v.text is None: value = None
                elif kind == 'e': raise ValueError('Excel error cell')
                elif kind == 'str': value = v.text
                else:
                    value = int(v.text) if re.fullmatch(r'-?\d+', v.text) else float(v.text)
                values[loc] = value
            wanted = {'A1': name, 'A2': SUBTITLE}
            for r, row in enumerate([headers] + rows, 4):
                for c, value in enumerate(row, 1): wanted[address(r, c)] = value
            for loc, value in wanted.items():
                observed = values.get(loc)
                # Empty strings may be serialized as absent cells. No numeric
                # strings, booleans or nonempty literals receive coercion.
                if value == '' and observed is None: observed = ''
                if type(value) is not type(observed) or value != observed: raise ValueError(f'Cell mismatch {name}!{loc}: {value!r} != {observed!r}')
                checked += 1
            if any(v is not None and k not in wanted for k,v in values.items()): raise ValueError('Unexpected populated cell')
            row_counts.append(len(rows))
        if consumed != physical: raise ValueError('Unreferenced worksheet part')
    return dict(status='PASS_ALL_CELLS', sheets=len(expected), data_rows=row_counts, checked_cells=checked,
                formulas_allowed=False, financial_recomputation_performed=False, full_h_delivery_complete=False)
