"""Pure navigation relationship relocation for a separately bound repair overlay."""
import io,posixpath,re,zipfile
from pathlib import PureWindowsPath
import xml.etree.ElementTree as ET
M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def relocate_navigation(workbook_bytes,links,parent_root,output_root):
    require(type(workbook_bytes) is bytes and type(links) is list and len(links)==1632,'Full original task navigation')
    require(PureWindowsPath(parent_root).is_absolute() and PureWindowsPath(output_root).is_absolute() and PureWindowsPath(parent_root)!=PureWindowsPath(output_root),'Two explicit namespaces')
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as z:
        require(len(z.namelist())==len(set(z.namelist())),'Unique ZIP parts')
        def xml(name):
            b=z.read(name);require(b'<!DOCTYPE' not in b.upper() and b'<!ENTITY' not in b.upper(),'No XML declarations');return ET.fromstring(b)
        book=xml('xl/workbook.xml');rel=xml('xl/_rels/workbook.xml.rels');sheets=[s for s in book.findall('{'+M+'}sheets/{'+M+'}sheet') if s.get('name')=='全部任务'];require(len(sheets)==1,'Unique task navigation sheet')
        targets=[r for r in rel if r.get('Id')==sheets[0].get('{'+R+'}id')];require(len(targets)==1 and targets[0].get('TargetMode')!='External','Internal sheet')
        target=targets[0].get('Target');part=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target);require(re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part),'Fixed sheet part')
        sheet=xml(part);relpart=posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels';rels=xml(relpart)
        by={r.get('Id'):r for r in rels};require(len(by)==len(rels),'Unique relationships');h=sheet.findall('{'+M+'}hyperlinks/{'+M+'}hyperlink');require(len(h)==1632,'All native links')
        used=set();seen=set()
        for i,(node,link) in enumerate(zip(h,links)):
            require(link['worksheet']=='全部任务' and link['cell']==node.get('ref')==f'H{i+2}' and link['location']==node.get('location'),'Original full link order and location')
            require(re.fullmatch('[a-f0-9]{64}',link['numerical_task_id']) and link['numerical_task_id'] not in seen,'Unique full task identity');seen.add(link['numerical_task_id'])
            rid=node.get('{'+R+'}id');require(rid in by and rid not in used,'One distinct native relation per task');used.add(rid);r=by[rid]
            require(r.get('Type')==R+'/hyperlink' and r.get('TargetMode')=='External' and re.fullmatch(r'package-\d{4}\.xlsx',r.get('Target','')),'Only original package relationship')
            expected=PureWindowsPath(link['expected_workbook_reference']['path']);new=link['target'];require(type(new) is str and '\\' not in new and not PureWindowsPath(new).is_absolute(),'Relative local link only')
            resolved=PureWindowsPath(posixpath.normpath((str(PureWindowsPath(output_root)).replace('\\','/')+'/'+new)))
            require(resolved==expected and expected.parent in (PureWindowsPath(parent_root),PureWindowsPath(output_root)) and expected.name==r.get('Target'),'Bounded original filename and explicit replacement destination')
            r.set('Target',new)
        require(all(r.get('Type')!=R+'/hyperlink' or r.get('Id') in used for r in rels),'No unaccounted hyperlink')
        changed=ET.tostring(rels,encoding='utf-8',xml_declaration=True);out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as w:
            for info in z.infolist():w.writestr(info,changed if info.filename==relpart else z.read(info.filename))
        result=out.getvalue()
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as a,zipfile.ZipFile(io.BytesIO(result)) as b:
        require(a.namelist()==b.namelist() and all(a.read(n)==b.read(n) for n in a.namelist() if n!=relpart),'Only native target relationship part changes')
    return result
