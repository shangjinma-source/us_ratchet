"""Create-only bounded raw-return storage utility, not an execution worker.

A value is supplied by the caller; this module cannot attest how it was obtained.
No evaluator, source authentication, resource sufficiency or dispatch is granted.
"""
import hashlib,json,os
from pathlib import Path
from backtest import ndx_double_replacement_compressed_batch_research as codec

FLAGS=dict(source_bytes_authenticated=False,call_event_authenticated=False,evaluation_called=False,economic_result_validated=False,resource_sufficiency_proved=False,execution_authorized=False,automatic_retry_allowed=False)
def error(e):
 try:message=str(e)
 except BaseException as failure:message='ERROR_STRING_FAILED: '+type(failure).__name__
 return dict(type=type(e).__name__,message=message)
def filehash(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save_json(path,value):
 b=codec.encode(value)
 with path.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 codec.require(path.read_bytes()==b,'Exact durable metadata')
 return dict(path=str(path),sha256=hashlib.sha256(b).hexdigest(),byte_count=len(b))
def preserve_return(*,directory,descriptor,value,max_compressed_bytes,max_uncompressed_bytes):
 """Save canonical gzip before a caller may validate the numerical result.

    The existing directory may contain the caller's already durable START.
    Partial bytes are never deleted/truncated; repeat invocations are refused.
 """
 folder=Path(directory)
 codec.require(folder.is_dir()and not folder.is_symlink()and not getattr(folder,'is_junction',lambda:False)(),'Existing bounded output directory')
 names=('raw_return.json.gz','raw_receipt.json','raw_diagnostic.json')
 codec.require(not any((folder/n).exists()or(folder/n).is_symlink()for n in names),'Create-only raw attempt; no retry')
 codec.require(type(descriptor)is dict and set(descriptor)=={'schema','plan_sha256','batch_index','start','stop','point_count'},'Exact batch descriptor')
 codec.require(descriptor['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1','Batch descriptor schema')
 for key in ('batch_index','start','stop','point_count'):codec.integer(descriptor[key])
 codec.source_ref(dict(path='plan',sha256=descriptor['plan_sha256']))
 codec.require(descriptor['stop']-descriptor['start']==descriptor['point_count']and 0<descriptor['point_count']<=10000,'Bounded complete descriptor span')
 # These are explicit engineering limits, not a proof that real storage suffices.
 for limit in(max_compressed_bytes,max_uncompressed_bytes):codec.require(type(limit)is int and limit>0,'Pre-open positive limits')
 frozen_descriptor=json.loads(codec.encode(descriptor));raw_path=folder/names[0]
 try:
  with raw_path.open('xb')as f:
   try:metadata=codec.write_canonical_gzip(value,f,max_compressed_bytes=max_compressed_bytes,max_uncompressed_bytes=max_uncompressed_bytes)
   finally:f.flush();os.fsync(f.fileno())
  codec.require(filehash(raw_path)==metadata['compressed_sha256']and raw_path.stat().st_size==metadata['compressed_byte_count'],'Durable compressed bytes')
  raw_reference=dict(path=str(raw_path),sha256=metadata['compressed_sha256'],byte_count=metadata['compressed_byte_count'])
  receipt=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_RAW_RECEIPT_V1',status='COMPLETE_CANONICAL_JSON_GZIP_NOT_ECONOMICALLY_VALIDATED',descriptor=frozen_descriptor,descriptor_sha256=codec.digest(frozen_descriptor),raw_reference=raw_reference,codec_metadata=metadata,returned_value_supplied_by_caller=True,result_preserved_as_json=True,**FLAGS)
  r=save_json(folder/names[1],receipt)
  codec.require(filehash(raw_path)==metadata['compressed_sha256'],'Final original raw bytes')
  return r
 except BaseException as e:
  try:representation=repr(value);representation_error=None
  except BaseException as re:representation=None;representation_error=error(re)
  partial=None
  if raw_path.exists():partial=dict(path=str(raw_path),sha256=filehash(raw_path),byte_count=raw_path.stat().st_size)
  save_json(folder/names[2],dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_RAW_DIAGNOSTIC_V1',status='PARTIAL_OR_FAILED_RAW_DO_NOT_RETRY',descriptor=frozen_descriptor,returned_value_supplied_by_caller=True,result_preserved_as_complete_json=False,result_type=type(value).__name__,result_representation=representation,representation_is_original_json=False,representation_error=representation_error,error=error(e),preserved_raw_file=partial,**FLAGS))
  raise
