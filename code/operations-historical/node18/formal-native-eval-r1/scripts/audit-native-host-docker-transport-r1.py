"""Derived qualification of a native Docker SSH failure miswrapped as CLI exit.

Only trusted Result.exception_info is inspected. Recorder and tool text are not
inputs. Raw Results/rewards and prior Recorder qualification are never rewritten.
"""
import hashlib
import json
from pathlib import Path
import re


REASON = 'HOST_DOCKER_SSH_TRANSPORT_FAILURE'
_SSH_FAILURE = re.compile(
    r'command \[ssh -l (?P<user>[A-Za-z0-9_.-]+) -p (?P<port>[1-9][0-9]{0,4}) '
    r'-o ConnectTimeout=(?P<connect_timeout>[1-9][0-9]*) -T -- '
    r'(?P<host>[A-Za-z0-9_.:\[\]-]+) docker system dial-stdio\] '
    r'has exited with exit status 255, make sure the URL is valid, and '
    r'Docker 18\.09 or later is installed on the remote host: stderr='
    r'(?P<ssh_stderr>[^\x00]*)\Z'
)


def classify_raw(result):
    """Recognize the confirmed native envelope, not mentions within tool output."""
    error = result.get('exception_info') or {}
    if error.get('exception_type') != 'NonZeroAgentExitCodeError':
        return None
    message = error.get('exception_message')
    if not isinstance(message, str):
        return None
    parts = message.split('\n', 2)
    if len(parts) != 3 or not re.fullmatch(r'Command failed \(exit 1\): [^\r\n]+', parts[0]):
        return None
    if parts[1] not in ('stdout: None', 'stdout: ') or not parts[2].startswith('stderr: '):
        return None
    match = _SSH_FAILURE.fullmatch(parts[2].removeprefix('stderr: '))
    if match is None or int(match['port']) > 65535:
        return None
    return dict(reason=REASON, docker_client_exit=1, ssh_dial_stdio_exit=255,
                ssh_user=match['user'], ssh_host=match['host'], ssh_port=int(match['port']),
                exception_message_sha256=hashlib.sha256(message.encode()).hexdigest(),
                boundary='trusted_native_result_exception_header_and_terminal_stderr',
                recorder_or_tool_text_inspected=False)


def qualify_cached_row(row, result_path):
    """Reuse audited Recorder rows; read only the SHA-matching small native Result."""
    updated = dict(row)
    try:
        data = Path(result_path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row['result_sha256']:
            raise ValueError('Native Result SHA differs from the audited row')
        result = json.loads(data)
        if str(result['id']) != str(row['trial_id']) or result['trial_name'] != row['trial_name']:
            raise ValueError('Native Result identity differs from the audited row')
        evidence = classify_raw(result)
        updated.update(host_docker_transport_failure=evidence is not None,
                       pre_host_transport_raw_official_score_valid=row.get(
                           'pre_host_transport_raw_official_score_valid', row['raw_official_score_valid']),
                       host_docker_transport_qualification=dict(
                           native_result_sha256=digest,
                           qualification_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           original_reader_audit_sources=row.get('reader_audit_sources'),
                           recorder_reaudited=False, native_result_or_reward_modified=False,
                           native_failure=evidence))
        if evidence is not None:
            # R8 already rejects false here. Preserve the prior derived value
            # separately; the native numeric reward and error list are untouched.
            updated.update(raw_official_score_valid=False, valid_score=False,
                           task_success=False, diagnostic_exclusion_reason=REASON)
    except Exception as error:
        # An unverified source cannot silently become a model zero or success.
        updated.update(valid_score=False, task_success=False,
                       audit_error='HostDockerQualification: '+repr(error),
                       diagnostic_exclusion_reason='HOST_DOCKER_QUALIFICATION_SOURCE_UNVERIFIED')
    return updated
