"""Offline immutable input-root copy; does not edit runtime config or source caches."""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
from uuid import uuid4


def relative_name(name):
    normalized=name.replace('\\','/')
    path=PurePosixPath(normalized)
    if path.is_absolute() or '..' in path.parts or ':' in normalized or not normalized:
        raise ValueError('PUBLICATION_SOURCE_PATH_INVALID:'+normalized)
    return normalized


def discover(root,entrypoints,follow_references=True):
    root=Path(root).resolve();pins={};sizes={};queue=list(entrypoints.items());absolute_bindings={}
    def references(value):
        if isinstance(value,dict):
            sources=value.get('source_hashes',{})
            if isinstance(sources,dict):
                queue.extend((p,h) for p,h in sources.items() if isinstance(p,str) and isinstance(h,str))
            for row in value.get('source_references',[]) if isinstance(value.get('source_references',[]),list) else []:
                if isinstance(row,dict) and isinstance(row.get('path'),str) and isinstance(row.get('sha256'),str):
                    queue.append((row['path'],row['sha256']))
            for child in value.values():references(child)
        elif isinstance(value,list):
            for child in value:references(child)
    while queue:
        name,expected=queue.pop()
        if Path(name).is_absolute():
            resolved=Path(name).resolve()
            if not resolved.is_relative_to(root):raise ValueError('PUBLICATION_ABSOLUTE_SOURCE_OUTSIDE_ROOT')
            normalized=resolved.relative_to(root).as_posix();absolute_bindings[name]=normalized;name=normalized
        name=relative_name(name)
        if name in pins:
            if pins[name]!=expected:raise ValueError('PUBLICATION_HASH_CONFLICT:'+name)
            continue
        path=root/name
        if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('PUBLICATION_SYMLINK_OR_OUTSIDE_ROOT')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('PUBLICATION_SOURCE_CHANGED:'+name)
        pins[name]=expected;sizes[name]=len(raw)
        if follow_references and path.suffix.lower()=='.json':
            try:document=json.loads(raw)
            except (ValueError,UnicodeError):continue
            references(document)
    return dict(schema='ROA_IMMUTABLE_INPUT_ROOT_V1',entrypoints={relative_name(p):h for p,h in entrypoints.items()},
                source_hashes=dict(sorted(pins.items())),absolute_reference_bindings=absolute_bindings,
                absolute_reference_policy='Metadata bytes retained. Runtime must resolve these through publication bindings, never original mutable paths.',
                dependency_scope='RECURSIVE_HASH_REFERENCES' if follow_references else 'EXPLICIT_RUNTIME_INPUT_SET_NOT_RECURSIVE_CERTIFICATION',
                file_count=len(pins),total_bytes=sum(sizes.values()))


def verify(directory):
    directory=Path(directory).resolve();envelope=json.loads((directory/'publication.json').read_bytes())
    document=envelope['document']
    if sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=envelope['sha256']:
        raise ValueError('PUBLICATION_ENVELOPE_CHANGED')
    for name,expected in document['source_hashes'].items():
        path=directory/'inputs'/relative_name(name)
        if path.is_symlink() or not path.resolve().is_relative_to(directory/'inputs') or sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('PUBLICATION_INPUT_CHANGED:'+name)
    return document


def publish(*,root,entrypoints,destination,dry_run=False,follow_references=True):
    root=Path(root).resolve();destination=Path(destination).resolve();document=discover(root,entrypoints,follow_references)
    if dry_run:return document
    if destination.exists():raise ValueError('PUBLICATION_DESTINATION_EXISTS')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=destination.with_name(destination.name+'.staging-'+uuid4().hex)
    staging.mkdir()
    for name,expected in document['source_hashes'].items():
        raw=(root/name).read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('PUBLICATION_SOURCE_CHANGED_DURING_COPY:'+name)
        target=staging/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    envelope=dict(document=document,sha256=sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    (staging/'publication.json').write_text(json.dumps(envelope,indent=2),encoding='utf8')
    verify(staging)
    staging.rename(destination)
    return dict(document,bundle_path=str(destination),input_root=str(destination/'inputs'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--entrypoints',required=True,help='JSON path -> approved SHA map')
    parser.add_argument('--destination',required=True)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--explicit-input-set',action='store_true',help='Input map must enumerate every actual runtime dependency; does not certify recursive history')
    parser.add_argument('--report')
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    result=publish(root=root,entrypoints=json.loads((root/args.entrypoints).read_bytes()),destination=root/args.destination,dry_run=args.dry_run,follow_references=not args.explicit_input_set)
    if args.report:(root/args.report).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('file_count','total_bytes')}))


if __name__=='__main__':main()
