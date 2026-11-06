"""Server-owned monthly preparation pipeline; never switches active configuration."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from scripts.research.run_roa_monthly_capture import run as run_capture
from scripts.research.coordinate_roa_monthly_offline import coordinate


def bounded(root, name):
    p=Path(name)
    if p.is_absolute() or ".." in p.parts or ":" in name:
        raise ValueError("PIPELINE_PATH_INVALID")
    p=(root/p).resolve()
    if p==root or not p.is_relative_to(root):raise ValueError("PIPELINE_PATH_INVALID")
    return p


def check(root, reference):
    raw=bounded(root,reference["path"]).read_bytes()
    if sha256(raw).hexdigest()!=reference["sha256"]:raise ValueError("PIPELINE_SOURCE_CHANGED:"+reference["path"])
    return json.loads(raw)


def publish(**kwargs):
    from scripts.research.prepare_roa_monthly_publication import prepare_publication
    return prepare_publication(**kwargs)


def _run(*,root,request,execute=False,clock=lambda:datetime.now(timezone.utc),fetch=None):
    root=Path(root).resolve();stage="REQUEST"
    try:
        if set(request)!={"capture","active","package","coordination_directory","publication_directory"}:
            raise ValueError("PIPELINE_REQUEST_FIELDS")
        if set(request["package"])!={"session_calendar","training_calendar","expected_month"}:
            raise ValueError("PIPELINE_PACKAGE_FIELDS")
        if request["package"]["training_calendar"]!=request["capture"]["training_calendar"]:
            raise ValueError("PIPELINE_TRAINING_CALENDAR_CONFLICT")
        bounded(root,request["coordination_directory"]);bounded(root,request["publication_directory"])
        check(root,request["active"])
        stage="CAPTURE_AND_TRAINING"
        arguments=dict(root=root,request=request["capture"],capture=execute,clock=clock)
        if fetch is not None:arguments["fetch"]=fetch
        captured=run_capture(**arguments)
        if captured["status"]=="WAIT_COMPLETED_MONTH_END":
            return dict(status=captured["status"],stage=stage,http_calls=0,formal_gate_calls=0,activated=False)
        if not execute:
            return dict(status="DRY_RUN_NO_PREPARATION",stage=stage,http_calls=0,formal_gate_calls=0,activated=False)
        if captured["status"] not in ("PREPARED_VERIFIED_NOT_ACTIVATED","VERIFIED_COMPLETION_REUSED"):
            raise ValueError("CAPTURE_NOT_VERIFIED")
        directory=bounded(root,request["capture"]["output_directory"])
        seal=json.loads((directory/"runner_receipt.json").read_bytes())
        name=(directory/"manifest.json").relative_to(root).as_posix()
        reference=dict(path=name,sha256=seal["output_hashes"][name])
        manifest=check(root,reference)
        check(root,request["active"])
        stage="MONTH_PACKAGE_AND_REGISTRATION"
        coordinated=coordinate(root=root,request=dict(active=request["active"],decision_date=manifest["decision_date"],
            package=dict(request["package"],manifest=reference),output_directory=request["coordination_directory"]),now=clock())
        if coordinated["status"]!="PREPARED_REGISTRATION_NOT_ACTIVATED":
            return dict(status=coordinated["status"],stage=stage,activated=False)
        check(root,request["active"])
        stage="FORMAL_PUBLICATION_PREFLIGHT"
        # Every invocation re-runs the formal gate; prior validation is never a shortcut.
        attempt=request["publication_directory"].rstrip("/")+"/attempt-"+uuid4().hex
        validated=publish(root=root,active=request["active"],registration=coordinated["registration"],output_directory=attempt)
        check(root,request["active"])
        return dict(status=validated["status"],stage=stage,publication_directory=attempt,
                    http_calls=captured.get("http_calls",0),formal_gate_scope="CURRENT_AND_PROPOSED_V34",
                    activated=False,account_writes=False,schedules_changed=False)
    except Exception as error:
        return dict(status="FAILED_NOT_ACTIVATED",stage=stage,error=str(error),activated=False,
                    automatic_retry=False,retained_outputs=True)


def run(*,root,request,execute=False,clock=lambda:datetime.now(timezone.utc),fetch=None):
    if not execute:
        return _run(root=root,request=request,execute=False,clock=clock,fetch=fetch)
    root=Path(root).resolve()
    token=uuid4().hex
    try:
        # Serialize all ROA month preparation runs in this workspace, even if requests
        # use different output directories but share the same capture plan.
        bounded(root,request["capture"]["output_directory"])
        lock=bounded(root,"tmp/roa_monthly_pipeline_execution.lock")
        reports=bounded(root,request["coordination_directory"])/"pipeline-reports"
        lock.parent.mkdir(parents=True,exist_ok=True)
        try:
            with lock.open("x",encoding="utf-8") as stream:
                json.dump(dict(token=token,request_sha256=sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
                               started_at=clock().isoformat()),stream)
        except FileExistsError:
            return dict(status="BUSY_OR_NEEDS_LOCK_RECONCILIATION",stage="PIPELINE_LOCK",activated=False,
                        automatic_retry=False,lock_path=lock.relative_to(root).as_posix())
        try:
            try:
                result=_run(root=root,request=request,execute=True,clock=clock,fetch=fetch)
            except Exception as error:
                result=dict(status="FAILED_NOT_ACTIVATED",stage="UNEXPECTED_PIPELINE_ERROR",error=str(error),activated=False,automatic_retry=False)
            reports.mkdir(parents=True,exist_ok=True)
            path=reports/(token+".json")
            result=dict(result,report_path=path.relative_to(root).as_posix(),finished_at=clock().isoformat())
            with path.open("x",encoding="utf-8") as stream:json.dump(result,stream,indent=2,sort_keys=True)
            return result
        finally:
            # Never remove a replacement or pre-existing lock belonging to another run.
            if lock.is_file() and json.loads(lock.read_bytes()).get("token")==token:
                lock.unlink()
    except Exception as error:
        return dict(status="FAILED_NOT_ACTIVATED",stage="PIPELINE_LOCK_OR_REPORT",error=str(error),
                    activated=False,automatic_retry=False)


def exit_code(result):
    """A scheduler must not treat a failed preparation as successful execution."""
    if result["status"] in {
        "WAIT_COMPLETED_MONTH_END", "WAIT_REQUIRED_MONTH_INPUT",
        "DRY_RUN_NO_PREPARATION", "VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED",
    }:
        return 0
    return 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--request",required=True,help="Trusted server-owned request, never client-supplied")
    parser.add_argument("--run",action="store_true",help="Permit capture and preparation; never activation")
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    location=Path(args.request).resolve()
    if not location.is_relative_to(root):raise ValueError("REQUEST_OUTSIDE_ROOT")
    result=run(root=root,request=json.loads(location.read_bytes()),execute=args.run)
    print(json.dumps(result,indent=2))
    return exit_code(result)


if __name__=="__main__":raise SystemExit(main())
