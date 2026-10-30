"""Exposed development-case builder and a separate exact event-state oracle.

It never imports the memory implementation. Every emitted case is development
material. These cases are ineligible for a future held-out scientific battery.
"""
import copy
import hashlib


def development_cases():
    p={"source":"synthetic-development","locator":"row-1",
       "sha256":hashlib.sha256(b"synthetic-development").hexdigest()}
    def put(i,key,value,**extra):
        return {"op":"put","id":i,"key":key,"value":value,"provenance":copy.deepcopy(p),**extra}
    cases=[
        ("updates",[put('m1','Aster.color','blue'),put('m2','Aster.color','green',supersedes='m1')],'Aster.color'),
        ("earlier_failures",[put('m1','Aster.failure','jam-17',protected=True),put('m2','Beryl.setting','normal')],'Aster.failure'),
        ("multisession_exact",[put('m1','Aster.serial','SYNTH-041'),{'op':'restart'}],'Aster.serial'),
        ("absent_evidence",[put('m1','Aster.color','blue')],'NeverRecorded.fact'),
        ("contradictions",[put('m1','Aster.color','blue'),put('m2','Aster.color','green')],'Aster.color'),
        ("provenance",[put('m1','Aster.color','blue')],'Aster.color'),
        ("corrupt_storage",[put('m1','Aster.color','blue'),{'op':'corrupt','kind':'truncation'}],'Aster.color'),
        ("capacity_pressure",[put(f'm{i}',f'fixture.{i}',f'value-{i}',protected=True) for i in range(4)],'fixture.3'),
    ]
    return [{"id":"EXPOSED-"+family,"family":family,"split":"development",
             "participant_seen":True,"events":events,"query_key":key}
            for family,events,key in cases]


def oracle(case):
    """Reference world state of all incoming evidence, not policy-admitted subset.

    Keeping refused events in this world prevents denominator selection in a
    future full-policy comparison. Independent review of this oracle is pending.
    """
    if case.get('split')!='development' or case.get('participant_seen') is not True:
        raise ValueError('only exposed development cases enabled')
    rows={}
    corrupt=False
    for event in case['events']:
        op=event['op']
        if op=='put':
            i=event['id']
            if i in rows:raise ValueError('duplicate event ID')
            old=event.get('supersedes')
            if old is not None:
                if old not in rows or rows[old]['status']!='current' or rows[old]['key']!=event['key']:
                    raise ValueError('invalid reference correction')
                rows[old]['status']='superseded'
            rows[i]={**copy.deepcopy(event),'status':'current'}
        elif op=='revoke':
            if event['target'] not in rows or rows[event['target']]['status']!='current':
                raise ValueError('invalid reference revocation')
            rows[event['target']]['status']='revoked'
        elif op=='restart':
            pass
        elif op=='corrupt':
            corrupt=True
        else:raise ValueError('unknown reference event')
    if corrupt:return {'status':'STORAGE_ERROR','gold_ids':[]}
    rs=[r for r in rows.values() if r['key']==case['query_key'] and r['status']=='current']
    if not rs or len({r['value'] for r in rs})!=1:
        return {'status':'UNKNOWN','gold_ids':[r['id'] for r in rs]}
    return {'status':'KNOWN','value':rs[0]['value'],'gold_ids':[r['id'] for r in rs],
            'provenance':[r['provenance'] for r in rs]}
