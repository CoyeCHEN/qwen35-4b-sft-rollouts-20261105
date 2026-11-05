"""Route exactly two independently reproduced invalid-JSON observations."""
import hashlib
from pathlib import Path
import quarantine_unrepresentable_export_r164 as first
import quarantine_unrepresentable_export_r244 as second

REVIEWERS={
    first.TRIAL:(first,'caf3172a7c921eabda6de14f3d588e2f2ed794a6d4445039cb3df625b07c8867'),
    second.TRIAL:(second,'6314e005be0fb2634f6b36bb289309d9646ae18b6339f0373ca48849f5cf89ab'),
}


def review(item,export):
    entry=REVIEWERS.get(item['trial_id'])
    if entry is None:raise ValueError('Unreviewed export error remains pending')
    module,expected=entry
    if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()!=expected:
        raise ValueError('Reviewed invalid-JSON source changed')
    return module.review(item,export)
