"""Durable capital-plan commitments; no account writes or trading authorization.

operation must lock account, classification, transfer and lifecycle evidence.
It yields the current server-built plan, never a browser-supplied plan.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sqlite3


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def plan_digest(value):
    return sha256(encoded(value).encode()).hexdigest()


class CapitalCommitmentStore:
    def __init__(self, *, path, account_id, operation):
        self.path=Path(path);self.account_id=account_id;self.operation=operation

    def initialize(self):
        with self.path.open('xb'):pass
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript('CREATE TABLE identity(account_id TEXT PRIMARY KEY); CREATE TABLE plans(plan_id TEXT PRIMARY KEY,payload TEXT NOT NULL); CREATE TABLE sources(funding_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL);')
            connection.execute('INSERT INTO identity VALUES (?)',(self.account_id,))
            connection.commit()

    def _read(self, connection):
        if connection.execute('SELECT account_id FROM identity').fetchall()!=[(self.account_id,)]:
            raise ValueError('CAPITAL_ACCOUNT_MISMATCH')
        plans={}
        for identifier,payload in connection.execute('SELECT plan_id,payload FROM plans ORDER BY plan_id'):
            plan=json.loads(payload)
            if plan_digest(plan)!=identifier or plan['account_id']!=self.account_id:
                raise ValueError('CAPITAL_PLAN_INTEGRITY')
            plans[identifier]=plan
        actual=dict(connection.execute('SELECT funding_id,plan_id FROM sources'))
        expected={}
        for identifier,plan in plans.items():
            for funding_id in plan['funding_ids']:
                if funding_id in expected:raise ValueError('CAPITAL_SOURCE_REUSED')
                expected[funding_id]=identifier
        if actual!=expected:raise ValueError('CAPITAL_SOURCE_INDEX_INVALID')
        return dict(plans=plans,revision=plan_digest(plans),account_mutated=False,executable=False)

    def read(self):
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            return self._read(connection)

    def commit(self, *, expected_revision, expected_plan_digest):
        with self.operation() as built:
            plan=deepcopy(built)
            if plan.get('account_id')!=self.account_id:raise ValueError('ACCOUNT_MISMATCH')
            identifiers=plan.get('funding_ids')
            if type(identifiers)is not list or not identifiers or any(type(i)is not str or not i for i in identifiers) or len(set(identifiers))!=len(identifiers):
                raise ValueError('CAPITAL_SOURCE_IDS_REQUIRED')
            identifier=plan_digest(plan)
            if identifier!=expected_plan_digest:raise ValueError('STALE_CAPITAL_PLAN')
            with closing(sqlite3.connect(self.path,timeout=5,isolation_level=None)) as connection:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    state=self._read(connection)
                    if identifier in state['plans']:
                        connection.rollback();return dict(plan_id=identifier,already_committed=True,account_mutated=False,executable=False)
                    if state['revision']!=expected_revision:raise ValueError('STALE_CAPITAL_COMMITMENTS')
                    used={i for old in state['plans'].values() for i in old['funding_ids']}
                    if used.intersection(identifiers):raise ValueError('CAPITAL_SOURCE_ALREADY_COMMITTED')
                    connection.execute('INSERT INTO plans VALUES (?,?)',(identifier,encoded(plan)))
                    connection.executemany('INSERT INTO sources VALUES (?,?)',[(i,identifier) for i in identifiers])
                    connection.commit()
                except BaseException:
                    connection.rollback();raise
            return dict(plan_id=identifier,already_committed=False,account_mutated=False,executable=False)
