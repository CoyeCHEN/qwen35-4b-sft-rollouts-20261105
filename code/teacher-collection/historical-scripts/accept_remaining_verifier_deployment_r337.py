"""Exact one-Task deployment delta; no Teacher dispatch or Task rewrite."""
import ast
import datetime
import json
from pathlib import Path

import collection_readiness_r20 as old
import collection_readiness_r21 as new
import run_collection_stream_r21 as controller

R = new.R
IDENT = 'machine-learning_20260419_065313_002'


def function(tree, name):
    return ast.dump(next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name), include_attributes=False)


def main():
    runtime = controller.validate_controller_runtime()
    if old.NODE != new.NODE or old.DEPLOYMENT['environment'] != new.DEPLOYMENT['environment']:
        raise ValueError('Native Engine or environment changed')
    for key in ['task_runtime_initialization','public_cli_bootstrap','controller_runtime','public_verifier_dependency_approvals149','public_image_bindings_mirror149','dependency_override','dependency_override_sha256','native_client_bin','native_client_ssh_sha256','native_ssh_pool','teacher_limit','hot_setup_buffer','native_lifecycle_capacity','preparation_concurrency']:
        if old.DEPLOYMENT[key] != new.DEPLOYMENT[key]:
            raise ValueError('Unrelated deployment changed: '+key)
    before=old.DEPLOYMENT['task_public_dependencies'];after=new.DEPLOYMENT['task_public_dependencies']
    if set(after)-set(before)!={IDENT} or any(after.get(key)!=value for key,value in before.items()) or set(new.DEPLOYMENT['new_native_acceptance_required_task_ids'])!={IDENT}:
        raise ValueError('Existing public dependency bindings or affected Task scope changed')
    old_readiness=ast.parse((R/'scripts/collection_readiness_r20.py').read_text());new_readiness=ast.parse((R/'scripts/collection_readiness_r21.py').read_text())
    if function(old_readiness,'native_config') != function(new_readiness,'native_config'):
        raise ValueError('Native config construction changed')
    old_tree=ast.parse((R/'scripts/run_collection_stream_r20.py').read_text())
    new_tree=ast.parse((R/'scripts/run_collection_stream_r21.py').read_text().replace("'r21'","'r20'"))
    for name in ['admitted_teacher','ended_agent','ended_teacher','stage','diagnostic','prepare']:
        if function(old_tree,name)!=function(new_tree,name):raise ValueError('Native lifecycle or budget callback changed')
    phase=json.loads((R/'checks/controller-r21-agent-phase-acceptance-r318.json').read_text())
    source=R/'scripts/run_collection_stream_r21.py'
    if not phase['passed'] or phase['controller_source_sha256']!=new.sha(source):raise ValueError('Native phase acceptance changed')
    path=R/'stream/signed-debian-native-acceptance17-r336/environment-outcomes'/(IDENT+'.json')
    accepted=json.loads(path.read_text())
    if accepted['status']!='ENV_READY' or accepted['deployment_config_sha256']!=new.CONFIG_SHA or accepted['model_calls'] or accepted['teacher_dispatches']:
        raise ValueError('Exact native original CLI/NOP acceptance is incomplete')
    row=accepted['admitted_task'];task=Path(row['prepared_task_path'])
    if new.sha(task/'task.toml')!=row['prepared_task_toml_sha256'] or new.sha(task/'instruction.md')!=row['instruction_sha256']:
        raise ValueError('Frozen Task changed')
    for artifact in row['verifier_files']:
        if new.sha(task/artifact['path'])!=artifact['sha256']:raise ValueError('Official verifier changed')
    native={}
    for kind in ['install','nop']:
        trial=Path(accepted['native_'+kind+'_trial']);result=trial/'result.json';value=json.loads(result.read_text())
        if new.sha(result)!=accepted[kind+'_result_sha256'] or not value['finished_at'] or value.get('exception_info') or value['infrastructure_errors']:
            raise ValueError('Original native Result changed or failed')
        native[kind]=dict(trial=str(trial),result_sha256=new.sha(result))
    for kind in ['teacher','install','nop']:
        a=old.native_config(row,kind).model_dump(mode='json');b=new.native_config(row,kind).model_dump(mode='json')
        a.pop('trial_name');b.pop('trial_name')
        extra=b['environment']['extra_docker_compose'].pop()
        if extra!=after[IDENT]['extra_docker_compose'][0]['path'] or a!=b:
            raise ValueError('Affected config changed beyond the one declared public mirror')
    # The constructor AST is identical and its only new per-Task input key is
    # IDENT. Every other Task follows the identical prior config path.
    entry=after[IDENT]
    for item in entry['extra_docker_compose']:
        compose=Path(item['path']);mount=json.loads(compose.read_text())['services']['main']['volumes'][0]
        if new.sha(compose)!=item['sha256'] or not mount['read_only'] or Path(mount['source']).parent!=compose.parent or new.sha(Path(mount['source']))!=entry['candidate_apt_source_sha256']:
            raise ValueError('Declared read-only public setup bytes changed')
    out=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),controller_source_sha256=new.sha(source),deployment_config_sha256=new.CONFIG_SHA,old_deployment_config_sha256=old.CONFIG_SHA,controller_runtime=runtime,native_results=native,affected_task_ids=[IDENT],unaffected_task_config_path_identical_by_ast_and_exact_deployment_map=True,teacher_budget_model_tools_timeouts_task_images_and_official_tests_unchanged=True,native_ready_receipt=str(path),native_ready_receipt_sha256=new.sha(path),helper_sha256={name:new.sha(R/'scripts'/name) for name in ['run_collection_stream_r21.py','collection_readiness_r21.py','collection_readiness_r20.py','collection_attempts_r8.py','collection_selection_r7.py']},teacher_admission_granted=False,model_calls=0,source_sha256=new.sha(Path(__file__)))
    new.freeze(R/'checks/controller-r21-offline-acceptance-r337.json',out);print(json.dumps(out))


if __name__=='__main__':main()
