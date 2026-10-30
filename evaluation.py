"""Scientific comparison preparation. No benchmark execution entry point."""
import argparse
import json
from pathlib import Path
from sml.memory import METHODS, digest, number

TASK_FAMILIES=("updates", "earlier_failures", "multisession_exact", "absent_evidence",
               "contradictions", "provenance", "corrupt_storage", "capacity_pressure")
METRICS=("retrieval_accuracy", "incorrect_recall", "correct_abstention", "peak_rss_bytes",
         "snapshot_bytes", "query_latency_ns", "write_latency_ns", "acknowledged_write_survival",
         "corruption_detection", "formation_refusal", "capacity_refusal")


def validate(protocol):
    fields={"schema","project","status","scientific_execution_authorized","arms",
            "budgets","task_families","metrics","splits","projection","negative_controls",
            "freeze","analysis"}
    if not isinstance(protocol,dict) or set(protocol)!=fields or protocol["schema"]!=1 or protocol["project"]!="SML":
        raise ValueError("invalid SML evaluation schema")
    if protocol["scientific_execution_authorized"] is not False:
        raise ValueError("preparation cannot grant scientific execution")
    if protocol["status"] not in ("DRAFT","FROZEN"):
        raise ValueError("invalid status")
    if protocol["arms"]!=list(METHODS):
        raise ValueError("all four comparison arms must be explicit")
    if protocol["task_families"]!=list(TASK_FAMILIES) or protocol["metrics"]!=list(METRICS):
        raise ValueError("missing task family or metric")
    budgets=protocol["budgets"]
    if set(budgets)!={"max_records","max_bytes","top_k","half_life_seconds","threshold","cpu_threads"}:
        raise ValueError("incomplete budgets")
    for k in ["max_records","max_bytes","top_k","cpu_threads"]:
        if type(budgets[k]) is not int or budgets[k]<1:
            raise ValueError("invalid integer budget")
    if budgets["max_bytes"]>16_000_000 or budgets["max_bytes"]<1024 or budgets["top_k"]>100:
        raise ValueError("budget outside component contract")
    number(budgets["half_life_seconds"],"half_life",1e-9)
    number(budgets["threshold"],"threshold",0,1)
    splits=protocol["splits"]
    if not isinstance(splits,dict) or set(splits)!={"development","heldout","replication"}:
        raise ValueError("incomplete split declarations")
    all_ids=set()
    for split,meta in splits.items():
        if not isinstance(meta,dict) or set(meta)!={"ids","custodian","commitment","exposed"}:
            raise ValueError("invalid split metadata")
        if not isinstance(meta["ids"],list) or not all(isinstance(x,str) and x for x in meta["ids"]):
            raise ValueError("invalid task IDs")
        if len(meta["ids"])!=len(set(meta["ids"])) or all_ids.intersection(meta["ids"]):
            raise ValueError("task identity reused across splits")
        all_ids.update(meta["ids"])
        if type(meta["exposed"]) is not bool or (split!="development" and meta["exposed"]):
            raise ValueError("held-out contamination")
        if meta["commitment"] is not None and (not isinstance(meta["commitment"],str) or len(meta["commitment"])!=64 or any(c not in '0123456789abcdef' for c in meta["commitment"])):
            raise ValueError("invalid split commitment")
    projection=protocol["projection"]
    if set(projection)!={"enabled","fit_split","basis_sha256"} or type(projection["enabled"]) is not bool:
        raise ValueError("invalid projection declaration")
    if projection["fit_split"]!="development":
        raise ValueError("projection may not fit held-out data")
    if projection["enabled"] and not projection["basis_sha256"]:
        raise ValueError("enabled projection needs frozen basis")
    if not isinstance(protocol["negative_controls"],list) or not protocol["negative_controls"]:
        raise ValueError("negative controls required")
    if not isinstance(protocol["analysis"],str) or not protocol["analysis"]:
        raise ValueError("analysis required")
    if set(protocol["freeze"])!={"frozen_at","artifact_sha256","independent_key_audit"}:
        raise ValueError("invalid freeze declaration")
    return True


def readiness(protocol):
    validate(protocol)
    blockers=[]
    if protocol["status"]!="FROZEN": blockers.append("protocol is a draft")
    for split in ["heldout","replication"]:
        s=protocol["splits"][split]
        if not s["ids"] or not s["custodian"] or not s["commitment"]:
            blockers.append(split+" battery/custodian/commitment missing")
    for k in ["frozen_at","artifact_sha256","independent_key_audit"]:
        if not protocol["freeze"][k]:blockers.append("missing "+k)
    return {"project":"SML","preparation_valid":True,"comparison_ready":not blockers,
            "scientific_execution_authorized":False,"protocol_sha256":digest(protocol),"blockers":blockers}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=["validate","readiness"])
    p.add_argument("protocol")
    args=p.parse_args(argv)
    try:
        result=readiness(json.loads(Path(args.protocol).read_text()))
        print(json.dumps(result,sort_keys=True))
        return 2 if args.command=="readiness" and not result["comparison_ready"] else 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print(json.dumps({"valid":False,"error":str(e)},sort_keys=True))
        return 1


if __name__=="__main__":raise SystemExit(main())
