"""Observe the existing native nine; its shared serving lifecycle belongs to common30."""
import importlib,time
legacy=importlib.import_module('phase_progression18_r14')
phase=importlib.import_module('diagnostic150-phase18-r1')
R=phase.R;E=phase.E;C=phase.C

def advance(owner,state):
    actual=legacy.remote('status');phase.save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    prep=actual['modes']['new11-install-preflight'].get('progress')or{}
    state['cli_install_preflight']={k:prep.get(k)for k in ['expected','terminal','ready','failed','actual_model_attempts']}
    item=actual['modes']['new-m1-epoch3-unstarted'];state['epoch3_original_five_native_continuation_running']=item
    state['epoch3_original_controller_oom']=dict(original_started=4,original_missing_results=2,original_unstarted=5,primary_interrupted_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED')
    orphans=item['original_orphans'];state['epoch3_original_orphan_closure']={k:v['terminal_evidence_exists']for k,v in orphans.items()}
    complete=item['complete'];path=C/'EPOCH3_ORIGINAL_NINE_LIFECYCLE_COMPLETE_R1.json'
    if complete and all(orphans[t]['terminal_evidence_exists']for t in ['regex-log','chess-best-move']):
        assert complete['terminal']==5 and complete['original_started_trials_rerun']==0
        if not path.exists():phase.save(path,dict(at=time.time(),status='TERMINAL_PARTIAL_ORIGINAL_NINE',native_results=7,original_controller_interrupted_unknown=2,denominator=9,continuation_terminal=complete,original_orphans=orphans,original_oom_snapshot_sha256=item['original_oom_snapshot_sha256'],serving_retained_for_same_checkpoint_common30=True,source_sha256=phase.sha(__import__('pathlib').Path(__file__))))
        state['epoch3_original_nine_lifecycle_complete']=phase.read(path)
    state['original_nine_observer_never_stops_serving_or_dispatches_trials']=True
