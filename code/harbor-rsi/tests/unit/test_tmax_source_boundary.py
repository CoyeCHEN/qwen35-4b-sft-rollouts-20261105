import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[2] / "adapters/tmax/adapter.py"
SPEC = importlib.util.spec_from_file_location("tmax_adapter", PATH)
assert SPEC is not None and SPEC.loader is not None
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def original_task(tmp_path, definition):
    source = tmp_path / "task_000001_abcd1234"
    source.mkdir()
    (source / "task.json").write_text(
        json.dumps(dict(name=source.name, description="Solve this original task."))
    )
    (source / "container.def").write_text(definition)
    (source / "test_initial_state.py").write_text(
        "def test_initial():\n    assert True\n"
    )
    (source / "test_final_state.py").write_text("def test_final():\n    assert False\n")
    return source


@pytest.mark.parametrize(
    "private",
    [
        "oracle_path",
        "ground_truth.csv",
        "audio.label.txt",
        "binary.algo.txt",
        "expected_report.txt",
        ".expected_buggy_commit",
        "truth.csv",
        "golden_timeline.json",
    ],
)
def test_private_setup_material_is_rejected_before_conversion(tmp_path, private):
    source = original_task(
        tmp_path,
        "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\necho x > /app/" + private,
    )
    with pytest.raises(
        adapter.TaskPreparationError, match="PRIVATE_MATERIAL_IN_AGENT_BUILD"
    ):
        adapter.inspect_source(source, SimpleNamespace())


def test_missing_fixture_cannot_be_silently_skipped_by_native_converter(tmp_path):
    source = original_task(
        tmp_path, "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\ntrue\n"
    )
    native = SimpleNamespace(
        parse_files_section=lambda _: [("/old/fixtures/missing.png", "/app/input.png")],
        _resolve_fixture_src=lambda *_: None,
    )
    with pytest.raises(
        adapter.TaskPreparationError, match="Unresolved original fixture"
    ):
        adapter.inspect_source(source, native)


def test_absolute_host_fixture_cannot_escape_trusted_task_source(tmp_path):
    source = original_task(
        tmp_path, "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\ntrue\n"
    )
    outside = tmp_path / "host-private.txt"
    outside.write_text("host content must never enter a task")
    native = SimpleNamespace(
        parse_files_section=lambda _: [(str(outside), "/app/input")],
        _resolve_fixture_src=lambda *_: outside,
    )
    with pytest.raises(adapter.TaskPreparationError, match="escaped"):
        adapter.inspect_source(source, native)


def test_converter_requires_the_exact_pinned_source(tmp_path):
    path = tmp_path / "converter.py"
    path.write_text("raise RuntimeError('must not execute')")
    with pytest.raises(adapter.TaskPreparationError, match="SHA256 mismatch"):
        adapter.load_native_converter(path)


def test_verifier_reference_matrix_is_not_allowed_in_teacher_image(tmp_path):
    source = original_task(
        tmp_path, "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\ntrue\n"
    )
    (source / "test_final_state.py").write_text(
        "def test_matrix():\n    reference_path = '/app/reference/true_cov_matrix.npy'\n"
    )
    with pytest.raises(adapter.TaskPreparationError, match="VERIFIER_PRIVATE_PATH"):
        adapter.inspect_source(source, SimpleNamespace())


def test_explicit_original_input_is_not_a_hidden_verifier_answer(tmp_path):
    source = original_task(
        tmp_path, "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\ntrue\n"
    )
    (source / "task.json").write_text(
        json.dumps(
            dict(
                name=source.name, description="Read /app/data.csv and produce a report."
            )
        )
    )
    (source / "test_final_state.py").write_text(
        "def test_input():\n    expected_input_path = '/app/data.csv'\n"
    )
    receipt = adapter.inspect_source(
        source, SimpleNamespace(parse_files_section=lambda _: [])
    )
    assert receipt["task_id"] == source.name


def test_original_interactive_rc_startup_is_preserved_by_native_compose(tmp_path):
    source = original_task(
        tmp_path,
        'Bootstrap: docker\nFrom: ubuntu:22.04\n%post\necho "/app/server &" >> /etc/bash.bashrc\n',
    )
    original = (source / "container.def").read_bytes()
    main = adapter.runtime_compose_override(source)["services"]["main"]
    assert main["command"] == ["bash", "-ic", "exec sleep infinity"]
    assert main["working_dir"] == "/home/user" and main["environment"] == {
        "HOME": "/home/user"
    }
    assert (source / "container.def").read_bytes() == original


def test_no_interactive_override_when_original_task_does_not_need_it(tmp_path):
    source = original_task(
        tmp_path, "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\ntrue\n"
    )
    main = adapter.runtime_compose_override(source)["services"]["main"]
    assert main["command"] == ["bash", "-lc", "exec sleep infinity"]
    assert main["working_dir"] == "/home/user" and main["environment"] == {
        "HOME": "/home/user"
    }


def test_original_apptainer_environment_and_startscript_are_kept_in_order(tmp_path):
    environment = "if ! pgrep -f server.py; then python3 /app/server.py &\nfi"
    startup = "redis-server --daemonize yes\nnohup python3 /app/consumer.py &"
    source = original_task(
        tmp_path,
        "Bootstrap: docker\nFrom: ubuntu:22.04\n%environment\n"
        + environment
        + "\n%startscript\n"
        + startup
        + "\n%post\ntrue\n",
    )
    before = (source / "container.def").read_bytes()
    main = adapter.runtime_compose_override(source)["services"]["main"]
    assert main["command"] == [
        "bash",
        "-lc",
        "exec bash /usr/local/lib/tmax-original-startscript.sh",
    ]
    files = adapter.runtime_environment_files(source)
    assert environment + "\n" in files["/usr/local/lib/tmax-original-environment.sh"]
    assert (
        files["/usr/local/lib/tmax-original-startscript.sh"]
        == startup + "\nexec sleep infinity\n"
    )
    assert main["healthcheck"]["retries"] == 120
    assert (source / "container.def").read_bytes() == before


def test_task_static_environment_is_preserved_for_native_login_shells(
    tmp_path,
):
    source = original_task(
        tmp_path,
        "Bootstrap: docker\nFrom: ubuntu:22.04\n%environment\n# native Docker ENV\nexport PATH=/app/bin:$PATH\n%post\ntrue\n",
    )
    assert (
        "# native Docker ENV\nexport PATH=/app/bin:$PATH\n"
        in adapter.runtime_environment_files(source)[
            "/usr/local/lib/tmax-original-environment.sh"
        ]
    )
    assert adapter.runtime_compose_override(source)["services"]["main"]["command"] == [
        "bash",
        "-lc",
        "exec sleep infinity",
    ]


def test_interactive_rc_runs_after_original_apptainer_startup(tmp_path):
    source = original_task(
        tmp_path,
        "Bootstrap: docker\nFrom: ubuntu:22.04\n%post\necho start >> /etc/bash.bashrc\n"
        "%startscript\n/app/original-startup.sh\n",
    )
    assert adapter.runtime_compose_override(source)["services"]["main"]["command"] == [
        "bash",
        "-lc",
        "exec bash /usr/local/lib/tmax-original-startscript.sh",
    ]
    assert (
        adapter.runtime_environment_files(source)[
            "/usr/local/lib/tmax-original-startscript.sh"
        ]
        == "/app/original-startup.sh\nexec bash -ic 'exec sleep infinity'\n"
    )


def test_compose_cannot_substitute_controller_variables_into_original_startup(tmp_path):
    source = original_task(
        tmp_path,
        'Bootstrap: docker\nFrom: ubuntu:22.04\n%startscript\nprintf "%s" "$HOME ${TASK_ROOT} $$"\n',
    )
    command = adapter.runtime_compose_override(source)["services"]["main"]["command"]
    assert "$" not in command[-1]
    assert (
        adapter.runtime_environment_files(source)[
            "/usr/local/lib/tmax-original-startscript.sh"
        ]
        == 'printf "%s" "$HOME ${TASK_ROOT} $$"\nexec sleep infinity\n'
    )


@pytest.mark.skipif(
    sys.platform != "linux", reason="Executes Linux Bash environment inheritance"
)
def test_noninteractive_shell_receives_original_exports_without_reapplying_in_children(
    tmp_path,
):
    source = original_task(
        tmp_path,
        "Bootstrap: docker\nFrom: ubuntu:22.04\n%environment\n"
        "export TMAX_TEST_COUNTER=$((${TMAX_TEST_COUNTER:-0} + 1))\n"
        "export TMAX_TEST_VALUE=original-value\n",
    )
    script = tmp_path / "original-environment.sh"
    script.write_text(
        adapter.runtime_environment_files(source)[
            "/usr/local/lib/tmax-original-environment.sh"
        ]
    )
    task_env = dict(os.environ, BASH_ENV=str(script))
    task_env.pop("TMAX_ORIGINAL_ENV_LOADED", None)
    task_env.pop("TMAX_TEST_COUNTER", None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'printf "%s:%s\\n" "$TMAX_TEST_COUNTER" "$TMAX_TEST_VALUE"; '
            'bash -c \'printf "%s:%s\\n" "$TMAX_TEST_COUNTER" "$TMAX_TEST_VALUE"\'',
        ],
        env=task_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "1:original-value\n1:original-value\n"
