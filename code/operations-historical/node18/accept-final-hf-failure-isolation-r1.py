"""Exercise only the changed admission branch; never run a model or a Job."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import hashlib


ROOT = Path(__file__).parent


def changed_branch(tree):
    return next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                and ast.unparse(node.test) == "not (model / 'FINAL_HF_ADMISSION.json').exists()")


def main():
    original = ast.parse((ROOT / 'run-native772-advance-r16.py').read_text())
    updated = ast.parse((ROOT / 'run-native772-advance-r17.py').read_text())
    branch = copy.deepcopy(changed_branch(updated))
    body = ast.fix_missing_locations(ast.Module(body=[ast.For(
        target=ast.Name(id='stage', ctx=ast.Store()),
        iter=ast.List(elts=[ast.Constant(value='test-stage')], ctx=ast.Load()),
        body=[branch], orelse=[])], type_ignores=[]))
    # Prove every other statement, including all diagnostic dispatch, unchanged.
    changed_branch(original).body = [ast.Pass()]
    changed_branch(updated).body = [ast.Pass()]
    for tree in [original, updated]:
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == 'deployment_revision':
                node.value = ast.Constant(value='REVISION')
    assert ast.dump(original) == ast.dump(updated)
    cases = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        model = root / 'model'
        model.mkdir()
        (model / 'HF_EXPORT_COMPLETE.json').write_text('{}')
        marker = root / 'HF_ADMISSION_BLOCKER_test-stage.json'
        for case in ['preexisting_failure', 'new_failure', 'success', 'already_admitted']:
            marker.unlink(missing_ok=True)
            calls = []
            state = {}
            def run(*args, **kwargs):
                calls.append(args)
                if case == 'new_failure':
                    raise subprocess.CalledProcessError(1, ['native-admission'])
            if case == 'preexisting_failure':
                marker.write_text(json.dumps({'automatic_smoke_retry': False}))
            if case == 'already_admitted':
                (model / 'FINAL_HF_ADMISSION.json').write_text('{}')
            context = dict(model=model, C=root, R=ROOT, state=state, json=json,
                subprocess=types.SimpleNamespace(run=run, CalledProcessError=subprocess.CalledProcessError),
                sys=types.SimpleNamespace(executable='python'),
                time=types.SimpleNamespace(time=lambda: 1),
                sha256=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                atomic_json=lambda path, value: path.write_text(json.dumps(value)))
            exec(compile(body, '<admission-branch>', 'exec'), context)
            assert len(calls) == int(case in ['new_failure', 'success'])
            if case in ['preexisting_failure', 'new_failure']:
                assert state['status'] == 'NATIVE_COMPLETED_HF_ADMISSION_BLOCKED'
                assert state['diagnostics_continue'] and not state['automatic_smoke_retry']
            if case == 'new_failure':
                assert marker.exists() and json.loads(marker.read_text())['returncode'] == 1
            cases.append(case)
    print(json.dumps(dict(passed=True, cases=cases, model_or_task_calls=0,
        diagnostic_formal_nll_and_training_branches_unchanged=True)))


if __name__ == '__main__':
    main()
