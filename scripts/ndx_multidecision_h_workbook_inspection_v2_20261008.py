"""Independent complete literal/approximate cell inspection for the V2 workbook."""
from pathlib import PurePosixPath
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
SUBTITLE = '展示近似仅见主视图与曲线；全部精确原值另表保留。尚未晋级，不是新的OOS或PIT证明。'


def expected_sheets(payload):
    result = [('阅读说明', SUBTITLE, ['项目', '说明'], [
        ['交付内容', '真实股票及比例、16轨净值曲线、完整原风险与三种来源链暴露。'],
        ['未晋级原因', '缺独立cohort P50/P10/P90、正式逐项非劣比较及新前瞻OOS/PIT证据。'],
        ['近似边界', '主视图百分比和有效N显示两位小数；曲线采用binary64近似。精确原分数/Decimal/数量全部另表保留。'],
        ['空仓与阻断', '108个空仓日保留undefined；8条来源阻断路径未执行，不绘制假零曲线。'],
        ['数值来源', '原存控制连续链、已审候选连续派生链、原整股权重逐链相加分别标明，未重新归一。'],
        ['原证据说明', '原表中的历史阶段缺口声明保持原文，不能据此抹掉后来补充的证据，也不能冒称原先已完成。FX指汇率模式，lane指目标类型，SID指证券标识；尾部对应坏尾部，目标包络对应目标距离。'],
        ['长文本', '超长原JSON在原长文本分块页无损保存；主表保留精确定位。'],
        ['阅读顺序', '组合主视图 → 期末真实股票比例 → 曲线01至16 → 原始证据表。']])]
    chunks = []
    def add(table):
        indices = [i for i, name in enumerate(table['headers']) if not ('JSON' in name or '来源' in name)]
        indices += [i for i, name in enumerate(table['headers']) if 'JSON' in name or '来源' in name]
        rows = []
        for number, row in enumerate(table['rows'], 1):
            values = []
            for index in indices:
                value = row[index]
                if type(value) is str and len(value.encode('utf-16-le')) // 2 > 32767:
                    count = (len(value) + 13999) // 14000
                    for part in range(count): chunks.append([table['name'], number, index + 1, part + 1, count, value[part * 14000:(part + 1) * 14000]])
                    value = f'原长文本分块｜{table["name"]}｜数据行{number}｜原列{index+1}｜分块{count}'
                values.append(value)
            rows.append(values)
        result.append((table['name'], SUBTITLE, [table['headers'][i] for i in indices], rows))
    for table in payload['tables'][:2]: add(table)
    for chart in payload['charts']: result.append((chart['name'], chart['note'], chart['headers'], chart['rows']))
    for table in payload['tables'][2:]: add(table)
    result.append(('原长文本分块', SUBTITLE, ['原表', '数据行', '原列', '分块序号', '总分块', '原文本分块JSON'], chunks))
    return result


def address(row, column):
    letters = ''
    while column:
        column, digit = divmod(column - 1, 26);letters = chr(65 + digit) + letters
    return letters + str(row)


def inspect_workbook(path, payload):
    expected = expected_sheets(payload);checked = 0
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())): raise ValueError('Duplicate ZIP member')
        if any('externalLink' in n or n.endswith('vbaProject.bin') for n in archive.namelist()): raise ValueError('External/executable workbook')
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        relations = {}
        for item in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels')):
            if item.attrib.get('TargetMode') == 'External' or item.attrib['Id'] in relations: raise ValueError('Invalid worksheet relation')
            relations[item.attrib['Id']] = item.attrib['Target']
        sheets = ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS)
        if [s.attrib['name'] for s in sheets] != [e[0] for e in expected]: raise ValueError('Exact sheet inventory/order')
        physical = {name for name in archive.namelist() if re.fullmatch(r'xl/worksheets/[^/]+\.xml', name)}
        consumed = set()
        for sheet, (name, subtitle, headers, rows) in zip(sheets, expected):
            target = relations[sheet.attrib[RID]]
            member = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
            if '..' in PurePosixPath(member).parts or member not in physical or member in consumed: raise ValueError('Unique physical sheet')
            consumed.add(member);values = {}
            for cell in ET.fromstring(archive.read(member)).findall('s:sheetData/s:row/s:c', NS):
                location = cell.attrib['r'];kind = cell.attrib.get('t');node = cell.find('s:v', NS)
                if location in values or cell.find('s:f', NS) is not None: raise ValueError('Duplicate cell or formula')
                if kind == 's':
                    if node is None or node.text is None or not node.text.isdigit() or int(node.text) >= len(shared): raise ValueError('Shared text index')
                    value = shared[int(node.text)]
                elif kind == 'inlineStr': value = ''.join(cell.find('s:is', NS).itertext())
                elif kind == 'b':
                    if node is None or node.text not in ('0', '1'): raise ValueError('Exact boolean')
                    value = node.text == '1'
                elif kind == 'e': raise ValueError('Excel error')
                elif node is None or node.text is None: value = None
                elif kind == 'str': value = node.text
                else:
                    if kind not in (None, 'n'): raise ValueError('Literal numeric type')
                    value = int(node.text) if re.fullmatch(r'-?\d+', node.text) else float(node.text)
                values[location] = value
            wanted = {'A1': name, 'A2': subtitle}
            for r, row in enumerate([headers] + rows, 4):
                for c, value in enumerate(row, 1): wanted[address(r, c)] = value
            for location, value in wanted.items():
                observed = values.get(location)
                if value == '' and observed is None: observed = ''
                # Chart values alone are binary64 display approximations; their
                # integral values may be written with integer XML spelling.
                if type(value) is float and type(observed) is int: observed = float(observed)
                if type(value) is not type(observed) or value != observed: raise ValueError(f'Cell mismatch {name}!{location}')
                checked += 1
            if any(v is not None and k not in wanted for k, v in values.items()): raise ValueError('Extra populated cell')
        if consumed != physical: raise ValueError('Unreferenced worksheet')
    return dict(status='PASS_ALL_V2_CELLS', sheets=len(expected), data_rows=[len(x[3]) for x in expected], checked_cells=checked,
                formulas_allowed=False, financial_recomputation_performed=False, full_h_delivery_complete=False)
