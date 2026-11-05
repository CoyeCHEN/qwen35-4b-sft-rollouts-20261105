"""Execute both admission entries with mocked transport; no model/Job calls."""
import argparse
import ast
import copy
import contextlib
import io
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).parent
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fragments(name, predicate):
    return [ast.dump(node) for node in ast.walk(ast.parse((ROOT / name).read_text())) if predicate(node)]


def fixture_entry(extended):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'checks').mkdir()
        for name in ['ORIGINAL_TEACHER_11TOOLS_CONFIG.json']:
            shutil.copyfile(ROOT / 'checks' / name, root / 'checks' / name)
        model = root / 'model'
        model.mkdir()
        (model / 'HF_EXPORT_COMPLETE.json').write_text('{"complete_final_hf": true}')
        wheel = root / 'wheel.whl'
        wheel.write_text('cpu test placeholder')
        (root / 'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json').write_text(json.dumps(dict(wheel=str(wheel), wheel_sha256=WHEEL)))
        py = root / 'serve/bin/python'
        (root / 'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').write_text(json.dumps(dict(command=[
            'systemd-run', '--unit=old.service', str(py), '--model-path', str(model)])))
        (root / 'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json').write_text('{}')
        control = root / 'control'
        control.mkdir()
        (control / 'FORMAL_GPU_ALLOCATION.json').write_text(json.dumps(dict(gpu_uuids=['CPU_TEST_UUID'])))
        names = ['cold-hf-native-cli-smoke-r6.py', 'audit-native-cli-smoke-r4.py',
            'audit-native-cli-prefix-r1.py', 'admit-formal-native-cli18-r2.py',
            'audit-native-cli-smoke-r5.py', 'audit-native-cli-prefix-r2.py']
        for name in names:
            shutil.copyfile(ROOT / name, root / name)
        binding = dict(model_id='test-model', model_path=str(model), port=1,
            model_manifest=str(model / 'HF_EXPORT_COMPLETE.json'),
            weight_version=hashlib.sha256((model / 'HF_EXPORT_COMPLETE.json').read_bytes()).hexdigest(),
            actual_model_info={})
        fake_serving = types.SimpleNamespace(info=lambda tag: dict(binding))
        entry = 'admit-formal-native-cli18-r2.py' if extended else 'cold-hf-native-cli-smoke-r6.py'
        with patch.dict(sys.modules, {'cold-native-serving18-r2': fake_serving}):
            module = load(entry)
        module.R = root
        if not extended:
            module.C = control
            module.SERVER_PY = py
            module.HARNESS = root / 'harness/bin/open-harness'
        real_sha = module.sha
        def sha(path):
            path = Path(path)
            if path == wheel:
                return WHEEL
            if path.name == 'serving_chat.py':
                return 'b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
            return real_sha(path)
        executed = []
        def run(argv, **kwargs):
            executed.append(argv)
            if '--cwd' in argv:
                workspace = Path(argv[argv.index('--cwd') + 1])
                output = workspace.parent
                assert workspace.name == 'workspace' and kwargs['cwd'] == workspace
                assert list(workspace.iterdir()) == []
                config = json.loads((output / 'config.json').read_text())
                assert Path(config['sessionDir']).parent == output
                assert Path(config['recording']['directory']).parent == output
                assert (output / 'instruction.txt').exists()
                for name in ['config.json', 'instruction.txt', 'stdout.jsonl', 'recorder', 'sessions']:
                    assert not (workspace / name).exists()
                (workspace / 'protocol-check.txt').write_bytes(b'beta\n')
                if extended:
                    (workspace / 'bg-ok.txt').write_text('ready\n')
            if len(argv) > 1 and Path(str(argv[1])).name in ['audit-native-cli-smoke-r4.py', 'audit-native-cli-smoke-r5.py']:
                output = Path(argv[2])
                (output / 'NATIVE_CLI_AUDIT.json').write_text(json.dumps(dict(passed=True,
                    calls=[dict(actual_completion_tokens=1)] * 3,
                    actual_tool_names=['write', 'read', 'edit_patch', 'bash', 'bash_job', 'trajectory_read', 'finish'])))
            return types.SimpleNamespace(returncode=0)
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(dict(model_path=str(model))).encode()
        with patch.object(module, 'sha', sha), patch.object(module.subprocess, 'run', run), \
             patch.object(module.subprocess, 'check_output', return_value='0, CPU_TEST_UUID, 0\n'):
            if extended:
                proof = module.admit('new-m2-e5')
            else:
                with patch.object(module.urllib.request, 'urlopen', return_value=Response()), \
                     patch.object(sys, 'argv', [entry, str(model)]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.main()
                proof = json.loads((model / 'TOOL_PROTOCOL_SMOKE.json').read_text())
        assert proof['passed'] and proof['control_and_recording_outside_working_directory']
        assert len([argv for argv in executed if '--cwd' in argv]) == 1
        return dict(kind='extended' if extended else 'basic', mocked_entry_passed=True)


def main():
    literal = lambda node: isinstance(node, (ast.Assign, ast.AugAssign)) and any(
        isinstance(child, ast.Name) and child.id == 'prompt' for child in ast.walk(node))
    for old, new in [('cold-hf-native-cli-smoke-r5.py', 'cold-hf-native-cli-smoke-r6.py'),
                     ('admit-formal-native-cli18-r1.py', 'admit-formal-native-cli18-r2.py')]:
        assert fragments(old, literal) == fragments(new, literal), 'Do not simplify the task prompt'
        config = lambda node: isinstance(node, ast.Call) and ast.unparse(node.func) == 'config.update'
        assert fragments(old, config) == fragments(new, config), 'Protocol/budgets changed'
    for old, new in [('audit-native-cli-smoke-r2.py', 'audit-native-cli-smoke-r4.py'),
                     ('audit-native-cli-smoke-r3.py', 'audit-native-cli-smoke-r5.py')]:
        check = lambda node: isinstance(node, ast.Assert)
        a = fragments(old, check)
        b = fragments(new, check)
        # Only add layout assertions and relocate the existing background fixture.
        b = [item.replace("Name(id='workspace', ctx=Load())", "Name(id='output', ctx=Load())") for item in b]
        assert b[2:] == a
    final_old = (ROOT / 'final-hf-admission18-r4.py').read_text()
    assert (ROOT / 'final-hf-admission18-r5.py').read_text() == final_old.replace('cold-hf-native-cli-smoke-r5.py', 'cold-hf-native-cli-smoke-r6.py')
    phase_old = ast.parse((ROOT / 'phase_progression18_r12.py').read_text())
    phase_new = ast.parse((ROOT / 'phase_progression18_r13.py').read_text())
    funcs = lambda tree: {node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name != 'formal'}
    assert funcs(phase_old) == funcs(phase_new)
    old_nll = ast.parse((ROOT / 'new-validation-readouts18-r2.py').read_text())
    new_nll = ast.parse((ROOT / 'new-validation-readouts18-r3.py').read_text())
    old_advance = next(node for node in old_nll.body if isinstance(node, ast.FunctionDef) and node.name == 'advance')
    new_advance = copy.deepcopy(next(node for node in new_nll.body if isinstance(node, ast.FunctionDef) and node.name == 'advance'))
    old_branch = next(node for node in ast.walk(old_advance) if isinstance(node, ast.If) and ast.unparse(node.test) == 'epoch == 5')
    new_branch = next(node for node in ast.walk(new_advance) if isinstance(node, ast.If) and ast.unparse(node.test) == 'epoch == 5')
    new_branch.body = copy.deepcopy(old_branch.body)
    assert ast.dump(new_advance) == ast.dump(old_advance), 'The scorer/queue/unique rows must stay unchanged'
    # The NLL change admits only an actually sealed final model with cold GPU load.
    tree = ast.parse((ROOT / 'new-validation-readouts18-r3.py').read_text())
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'final_hf_ready_for_nll')
    context = dict(json=json, hashlib=hashlib)
    exec(compile(ast.Module(body=[func], type_ignores=[]), '<NLL readiness>', 'exec'), context)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)
        assert context['final_hf_ready_for_nll'](source, 125) is False
        export = source / 'HF_EXPORT_COMPLETE.json'
        export.write_text('{"complete_final_hf": true}')
        cold = source / 'HF_LOAD_SMOKE.json'
        cold.write_text(json.dumps(dict(model_loaded=True, generated_tokens=11,
            export_manifest_sha256=hashlib.sha256(export.read_bytes()).hexdigest())))
        (source / 'checkpoint-125').mkdir()
        (source / 'checkpoint-125/CHECKPOINT_COMPLETE.json').write_text('{}')
        (source / 'trainer_state.json').write_text('{"global_step": 125, "epoch": 5}')
        assert context['final_hf_ready_for_nll'](source, 125)
        cold.write_text('{"model_loaded": true, "generated_tokens": 11, "export_manifest_sha256": "bad"}')
        try: context['final_hf_ready_for_nll'](source, 125)
        except AssertionError: pass
        else: raise AssertionError('Wrong sealed identity accepted')
    entries = [fixture_entry(False), fixture_entry(True)]
    print(json.dumps(dict(passed=True, entries=entries, prompt_config_and_existing_audit_assertions_unchanged=True,
        nll_missing_rejected_sealed_accepted_wrong_sha_rejected=True,
        actual_model_or_task_calls=0, actual_gpu_imports_or_launches=0)))


if __name__ == '__main__':
    main()
