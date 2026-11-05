"""Record measured initial-test false negatives without altering any test."""
import datetime
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
ident='task_004361_0d2c270d'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    a=R/'stream/original-startup-process-observation17-r99/probes'/ident
    b=R/'stream/original-startup-pytest-process-observation17-r102/probes'/ident
    p=b/'subprocess_return_observations-stdout.txt'
    records=[json.loads(line) for line in p.read_text().splitlines()]
    measured=[]
    for row in records:
        if row['command']!=[['ps','aux']]:raise ValueError('Unexpected subprocess observation')
        measured.append(dict(command=row['command'],format_env=row['format_env'],
            exact_original_predicate_matches=any('report.py' in line and 'python' in line for line in row['result'].splitlines()),
            truncated_python_command_observed='python3 repor\n' in row['result']))
    live={}
    for label in ['original_declared_starter_runtime','original_initial_state_after_starter','no_reward_written']:
        path=a/(label+'-host-observation.json');value=json.loads(path.read_text())
        live[label]=dict(source=str(path),sha256=sha(path),
            real_original_process_observed='python3 report.py' in value['exec_ps']['stdout'],
            container_ids=value['container_ids'])
    if not all(x['real_original_process_observed'] for x in live.values()) or any(x['exact_original_predicate_matches'] or not x['truncated_python_command_observed'] for x in measured):
        raise ValueError('The measured truncation/liveness evidence changed')
    original=R/'sources/tmax/original-tasks'/ident
    value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),task_id=ident,
        status='ORIGINAL_PS_OUTPUT_TRUNCATION_MEASURED_NOT_MISSING_PROCESS',
        live_process_snapshots=live,subprocess_observation=str(p),subprocess_observation_sha256=sha(p),
        observations=measured,original_initial_test_sha256=sha(original/'test_initial_state.py'),
        original_container_def_sha256=sha(original/'container.def'),
        corrected_initial_candidate=str(R/'stream/original-process-format-native17-r103/initial-outcomes'/(ident+'.json')),
        trusted_initial_and_verifier_format_candidate={'COLUMNS':'4096'},
        teacher_environment_changed=False,original_goal_program_sql_tests_reward_changed=False,
        transient_native_transport_timeout_root_cause='Not proven; separate independent-SSH candidate has bounded eight-call same-Engine acceptance and still requires complete native CLI/NOP acceptance.',
        teacher_dispatches=0,model_calls=0,ready_granted_by_this_record=False)
    with (R/'checks/original-process-list-truncation-evidence-r110.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(task_id=ident,live_process_checks=len(live),measured_truncated_ps_returns=len(measured),ready_granted=False)))


if __name__=='__main__':main()
