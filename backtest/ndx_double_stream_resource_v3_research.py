"""Pure normal-output resource arithmetic; no domain/evaluation/IO entry points."""
import ast
import json
import sys


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def constructor(source, schema, environment):
    """Evaluate one pinned-source dictionary constructor, never its function body.

    Caller authenticates source and supplies a closed synthetic environment.
    No function definitions or statements from source are executed here.
    """
    environment = dict(environment)
    scope = environment.pop('__function__', None)
    tree = ast.parse(source)
    if scope is not None:
        tree = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == scope)
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'dict':
            if any(k.arg == 'schema' and isinstance(k.value, ast.Constant) and k.value.value == schema for k in node.keywords):
                candidates.append(node)
    if len(candidates) != 1:
        raise ValueError('Unique literal-schema dictionary constructor required')
    return eval(compile(ast.Expression(candidates[0]), '<pinned-constructor>', 'eval'),
                {'__builtins__': {'dict': dict, 'len': len, 'str': str, 'bool': bool}, **environment})


def normal_run_bound(total):
    assert type(total) is int and total > 0
    return len(encode(dict(start=total, stop=total, status='inspected_infeasible'))) + 1


def allocation_bytes(length, cluster):
    assert type(length) is int and length >= 0 and type(cluster) is int and cluster > 0
    return ((length + cluster - 1) // cluster) * cluster


def retained_tree_bytes(value):
    """No-sharing CPython payload model, not RSS/allocator/kernel allocation.

    Repeated objects are charged repeatedly. List pointer capacity is rounded up
    beyond CPython's ordinary append formula; dict sizes are actual getsizeof of
    the template or twice its next power-of-two entry-count table allowance.
    """
    if type(value) is dict:
        table = max(sys.getsizeof(value), 256 + 64 * (1 << max(1, len(value)).bit_length()))
        return table + sum(retained_tree_bytes(k) + retained_tree_bytes(v) for k, v in value.items())
    if type(value) in (list, tuple):
        return max(sys.getsizeof(value), 64 + 16 * (len(value) + 8)) + sum(map(retained_tree_bytes, value))
    if type(value) in (str, bytes, int, float, bool, type(None)):
        return sys.getsizeof(value)
    raise TypeError('Explicit JSON-shaped payload only')


def totals(*, count, batch_size, gzip_total, gzip_batch, raw_batch, file_lengths,
           manifest_line, audit_line, request_lengths, cluster=4096):
    assert all(type(x) is int and x > 0 for x in (count,batch_size,gzip_total,gzip_batch,raw_batch,cluster))
    batches = (count + batch_size - 1) // batch_size
    run_size = normal_run_bound(count)
    fixed = sum(file_lengths.values())
    # result.json is passed with []; each run adds object+comma, overcounting
    # the final comma. Other files/rows have no per-point payload.
    logical = gzip_total + count*run_size + batches*(fixed+manifest_line+audit_line) + sum(request_lengths.values())
    files = 7*batches + 7  # 7 batch files, worker4 and independent reader3
    directories = batches + (batches+999)//1000 + 5 + 1  # safe overcount
    data_cluster_upper = logical + files*(cluster-1)
    return dict(count=count,batch_size=batch_size,batch_count=batches,
                normal_run_bytes_per_point=run_size,normal_run_total=count*run_size,
                batch_fixed_metadata=file_lengths,manifest_line_upper=manifest_line,
                audit_line_upper=audit_line,request_metadata=request_lengths,
                normal_logical_bytes_upper=logical,normal_file_count=files,directory_count_upper=directories,
                normal_data_cluster_bytes_upper=data_cluster_upper,
                normal_batch_logical_upper=gzip_batch+batch_size*run_size+fixed+manifest_line+audit_line,
                ntfs_internal_metadata_upper=None,process_rss_upper=None,
                execution_authorized=False)
