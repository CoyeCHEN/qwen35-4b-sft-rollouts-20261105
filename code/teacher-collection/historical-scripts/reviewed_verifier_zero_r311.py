"""Apply four additional exact-Trial log reviews; keep original rewards intact."""
import functools
import hashlib
import json
from pathlib import Path

from reviewed_verifier_zero_r245 import apply_reviewed_zero as previous_reviews

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
MANIFEST = R / 'checks/reviewed-new-zero-r310.json'
EXPECTED = 'f0dabe19703aa831c37aea47a3cdd1714939e7a1a84658050dc3376c31fe9fea'
CLASSIFICATIONS = {
    'REVIEWED_VERIFIER_BOOTSTRAP_NETWORK_FAILURE': ('OFFICIAL_VERIFIER_BOOTSTRAP_NETWORK_FAILURE', True),
    'REVIEWED_REQUIRED_PACKAGE_NOT_AVAILABLE': ('OFFICIAL_VERIFIER_SUBMITTED_PROGRAM_DEPENDENCY_FAILURE', False),
    'REVIEWED_VERIFIER_SERVER_STARTUP_FAILURE_ROOT_CAUSE_UNOBSERVED': ('OFFICIAL_VERIFIER_TASK_SERVER_STARTUP_FAILURE_CAUSE_UNRESOLVED', None),
}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


@functools.cache
def reviews():
    if sha(MANIFEST) != EXPECTED:
        raise ValueError('Exact new-zero review manifest changed')
    entries = json.loads(MANIFEST.read_text())['entries']
    output = {entry['trial_id']: entry for entry in entries}
    if len(entries) != 4 or len(output) != 4:
        raise ValueError('Exact four-Trial review scope changed')
    return output


def apply_reviewed_zero(record):
    record = previous_reviews(record)
    review = reviews().get(record['trial_id'])
    if review is None:
        return record
    if any(record[key] != review[key] for key in ['trial_id', 'task_id', 'pool', 'result_sha256']) or record['result_path'] != review['result']:
        raise ValueError('New zero review refers to another original Result')
    if record['classification'] != review['original_index_classification'] or record['raw_reward'] != 0 or not record['verifier_actually_completed']:
        raise ValueError('New zero review cannot override another outcome')
    if record['qualified_success'] or record['is_primary_trajectory'] or record['native_exception'] or record['infrastructure_errors']:
        raise ValueError('New zero review is not the reviewed native completed zero')
    for path, identity in [('result', 'result_sha256'), ('verifier_log', 'verifier_log_sha256')]:
        if sha(Path(review[path])) != review[identity]:
            raise ValueError('Original newly reviewed verifier evidence changed')
    classification, infrastructure = CLASSIFICATIONS[review['reviewed_classification']]
    return dict(record, classification=classification, completed_verifier_zero_review=str(MANIFEST), completed_verifier_zero_review_sha256=EXPECTED, verifier_failure_reason=review['reviewed_reason'], scoring_infrastructure_failure_detected=infrastructure, official_reward_unmodified=True)
