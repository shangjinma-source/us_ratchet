"""Exact-byte research preservation and missing-only recovery; default check."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.research.publish_roa_immutable_inputs import publish, verify, relative_name


def safe(root,name):
    name=relative_name(name);path=root/name
    if name.split("/")[0] not in {"tmp","data","scripts","research_contracts"}:
        raise ValueError("NON_RESEARCH_SOURCE")
    if name.startswith("data/") and not name.startswith("data/cache/"):
        raise ValueError("PRIVATE_DATA_PATH_REJECTED")
    if any(part.lower() in {"strategy_account","browser","cookies","credentials","secrets",".env"} for part in Path(name).parts) or path.suffix.lower() in {".db",".sqlite",".sqlite3",".pem",".key"}:
        raise ValueError("SENSITIVE_PATH_REJECTED")
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("SOURCE_LINK_OR_OUTSIDE_ROOT")
    return path


def archive(*,root,source_list,source_list_sha256,destination):
    root=Path(root).resolve();raw=safe(root,source_list).read_bytes()
    if sha256(raw).hexdigest()!=source_list_sha256:raise ValueError("SOURCE_LIST_CHANGED")
    document=json.loads(raw)
    if document["schema"]!="EXACT_RESEARCH_SOURCE_LIST_V1":raise ValueError("SOURCE_LIST_SCHEMA")
    pins=dict(document["source_hashes"]);pins[source_list]=source_list_sha256
    for name,expected in pins.items():
        if sha256(safe(root,name).read_bytes()).hexdigest()!=expected:raise ValueError("SOURCE_CHANGED:"+name)
    target=(root/destination).resolve();base=root/"data/strategy_archives"
    if not target.is_relative_to(base) or target==base or any(p.is_symlink() for p in (target,*target.parents)):
        raise ValueError("ARCHIVE_DESTINATION_INVALID")
    publish(root=root,entrypoints=pins,destination=target,follow_references=False)
    result=verify(target)
    return dict(status="ARCHIVED_EXACT_DECLARED_RESEARCH_BYTES",files=result["file_count"],bytes=result["total_bytes"],
                publication_sha256=sha256((target/"publication.json").read_bytes()).hexdigest(),destination=destination)


def check_or_restore(*,root,directory,publication_sha256,restore=False):
    root=Path(root).resolve();directory=Path(directory).resolve()
    if sha256((directory/"publication.json").read_bytes()).hexdigest()!=publication_sha256:
        raise ValueError("ARCHIVE_PUBLICATION_CHANGED")
    document=verify(directory)  # Check every archived byte before touching original paths.
    missing=[]
    for name,expected in document["source_hashes"].items():
        path=safe(root,name)
        if path.exists():
            if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError("EXISTING_DIFFERENT_BYTES_REFUSE_OVERWRITE:"+name)
        else:missing.append(name)
    if restore:
        for name in missing:
            path=safe(root,name);raw=(directory/"inputs"/name).read_bytes()
            if sha256(raw).hexdigest()!=document["source_hashes"][name]:raise ValueError("ARCHIVE_CHANGED_DURING_RESTORE")
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as stream:stream.write(raw)
        for name,expected in document["source_hashes"].items():
            if sha256(safe(root,name).read_bytes()).hexdigest()!=expected:raise ValueError("RESTORED_SOURCE_CHANGED")
    return dict(status="RESTORED_MISSING_ONLY" if restore else "CHECKED_NO_WRITES",missing=missing,
                restored=len(missing) if restore else 0,files=len(document["source_hashes"]),original_paths_still_required=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("archive","check","restore"),default="check")
    parser.add_argument("--directory",required=True)
    parser.add_argument("--source-list");parser.add_argument("--source-list-sha256")
    parser.add_argument("--publication-sha256")
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    if args.mode=="archive":
        result=archive(root=root,source_list=args.source_list,source_list_sha256=args.source_list_sha256,destination=args.directory)
    else:
        result=check_or_restore(root=root,directory=root/args.directory,publication_sha256=args.publication_sha256,restore=args.mode=="restore")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
