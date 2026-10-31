//! AI-generated (ChatGPT): Task 3 bounded contract checks; synthetic data only.
use sml::json::Value;
use sml::store::{MemoryStore, PutOptions};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::os::unix::process::ExitStatusExt;
use std::sync::{Arc, Barrier, mpsc};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        let p=std::env::temp_dir().join(format!("sml-chatgpt-{}-{}",std::process::id(),SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()));
        fs::create_dir(&p).unwrap(); Self(p)
    }
}
impl Drop for Temp { fn drop(&mut self) { let _=fs::remove_dir_all(&self.0); } }
fn prov() -> Value {
    Value::Obj(BTreeMap::from([
        ("source".into(),Value::Str("synthetic-task3-rust".into())),
        ("locator".into(),Value::Str("case".into())),
        ("sha256".into(),Value::Str("a".repeat(64))),
    ]))
}
fn opts() -> PutOptions {
    let mut e=vec![0.0;384];e[0]=1.0;
    PutOptions { embedding:Some(e),..Default::default() }
}
fn open(d:&Path)->MemoryStore { MemoryStore::open(d,Box::new(||1000.0),None).unwrap() }
fn mutate(m:&MemoryStore,op:&str) {
    match op {
        "put" => {m.put("new","new",&prov(),&opts()).unwrap();},
        "correct" => {m.correct(1,"new",&prov(),&opts()).unwrap();},
        "revoke" => {m.revoke(1,"withdraw",&prov()).unwrap();},
        "compact" => {m.compact(0).unwrap();},
        _=>panic!("unknown operation"),
    }
}

#[test]
fn threads_with_separate_handles_preserve_exact_keys_and_ids() {
    let t=Temp::new();let d=t.0.join("store");
    MemoryStore::create(&d,100,500000,Box::new(||1000.0),None).unwrap();
    let gate=Arc::new(Barrier::new(6));let (tx,rx)=mpsc::channel();let mut handles=vec![];
    for worker in 0..6 {
        let path=d.clone();let gate=gate.clone();let tx=tx.clone();
        handles.push(std::thread::spawn(move|| {
            let m=open(&path);gate.wait();let mut ids=vec![];
            for n in 0..12 { ids.push(m.put(&format!("w{}.{}",worker,n),"v",&prov(),&opts()).unwrap()); }
            tx.send(ids).unwrap();
        }));
    }
    drop(tx);
    let mut acknowledged=vec![];
    for _ in 0..6 { acknowledged.extend(rx.recv_timeout(Duration::from_secs(20)).expect("writer failed or hung")); }
    for h in handles { h.join().unwrap(); }
    acknowledged.sort();assert_eq!(acknowledged,(1..=72).collect::<Vec<i64>>());
    let state=open(&d).snapshot().unwrap();
    let records=match state.get("records").unwrap(){ Value::Arr(a)=>a,_=>panic!() };
    assert_eq!(records.len(),72);
    let keys: BTreeSet<String>=records.iter().map(|r|r.get("key").unwrap().as_str().unwrap().to_string()).collect();
    let expected: BTreeSet<String>=(0..6).flat_map(|w|(0..12).map(move|n|format!("w{}.{}",w,n))).collect();
    assert_eq!(keys,expected);
    let mut stored:Vec<i64>=records.iter().map(|r|match r.get("id").unwrap(){Value::Int(i)=>*i,_=>panic!()}).collect();
    stored.sort();assert_eq!(stored,acknowledged);
    println!("threads=6 writes_each=12 acknowledged=72 exact_keys=72 ids=1..72 PASS");
}

// Helper, never counted as an ordinary passing test: parent invokes it explicitly.
#[test]
#[ignore = "SIGKILL child helper; invoked only by parent test with fixture environment"]
fn task3_kill_worker() {
    let d=PathBuf::from(std::env::var("SML_TASK3_DIR").unwrap());
    let stage=std::env::var("SML_TASK3_STAGE").unwrap();
    let op=std::env::var("SML_TASK3_OP").unwrap();
    let fault=Box::new(move|at:&str| {
        if at==stage { unsafe { libc::kill(libc::getpid(),libc::SIGKILL); } panic!("SIGKILL returned"); }
        Ok(())
    });
    let m=MemoryStore::open(d,Box::new(||1000.0),Some(fault)).unwrap();
    mutate(&m,&op);
    panic!("kill boundary not reached");
}

#[test]
fn sigkill_all_mutators_at_four_boundaries_matches_complete_snapshot() {
    for op in ["put","correct","revoke","compact"] {
        for (stage,new_visible) in [("partial_write",false),("after_file_fsync",false),("after_replace",true),("after_dir_fsync",true)] {
            let t=Temp::new();let d=t.0.join("store");let expected=t.0.join("expected");
            let m=MemoryStore::create(&d,20,200000,Box::new(||1000.0),None).unwrap();
            m.put("k","old",&prov(),&opts()).unwrap();
            let before=fs::read(d.join("memory.json")).unwrap();
            fs::create_dir(&expected).unwrap();fs::write(expected.join("memory.json"),&before).unwrap();
            mutate(&open(&expected),op);
            let after=fs::read(expected.join("memory.json")).unwrap();
            assert_ne!(before,after,"mutation must change state");
            let mut child=Command::new(std::env::current_exe().unwrap())
                .args(["--exact","task3_kill_worker","--ignored","--nocapture"])
                .env("SML_TASK3_DIR",&d).env("SML_TASK3_STAGE",stage).env("SML_TASK3_OP",op)
                .stdout(Stdio::null()).stderr(Stdio::inherit()).spawn().unwrap();
            let deadline=Instant::now()+Duration::from_secs(15);
            let status=loop {
                if let Some(s)=child.try_wait().unwrap(){break s;}
                if Instant::now()>deadline {let _=child.kill();let _=child.wait();panic!("{} {} hung",op,stage);}
                std::thread::sleep(Duration::from_millis(5));
            };
            assert_eq!(status.signal(),Some(libc::SIGKILL),"{} {}",op,stage);
            let actual=fs::read(d.join("memory.json")).unwrap();
            assert_eq!(actual,if new_visible {after}else{before},"{} {}",op,stage);
            open(&d).snapshot().unwrap();
            println!("op={} stage={} signal=9 complete_new_visible={} PASS",op,stage,new_visible);
        }
    }
}
