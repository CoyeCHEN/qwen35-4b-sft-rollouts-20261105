"""Read-only diagnosis of quarantined boundaries with the frozen tokenizer."""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

E = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
os.environ.update(CUDA_VISIBLE_DEVICES='', QWEN35_MODEL_PATH=str(S / 'student-tokenizer-r155'),
    HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1')
sys.path.insert(0, str(E / 'sft-code-weight-audit-r3'))
from sft.qwen35 import load_tokenizer, normalize_message

IDS = ['fc3e86cf-e0bf-48a0-8c71-e3adb44467ae', 'ab50c639-afee-43b3-ada1-67be7949c569',
       '2b6ff11d-304e-45f2-a3fe-cd56a9aa03ed', 'a9d89dd6-07b1-48df-85f3-bd995752c48d',
       'c94f1270-c3ec-422a-bfb0-89e2dce2ef35', '8f42b40e-deae-429c-874e-5cf488c0c665']


def main():
    tokenizer = load_tokenizer()
    decode = lambda ids: tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    rows = []
    for ident in IDS:
        original = E / 'validation/stream-r3' / ident
        candidates = [S / 'data-canonical-trials-r163' / ident, original]
        root = next(p for p in candidates if (p / 'checks/canary-qwen-projection-all-v4.json').exists())
        report = json.loads((root / 'checks/canary-qwen-projection-all-v4.json').read_text())[0]
        error = next(x for x in report['errors'] if x['error'] == 'Generation-boundary tokenization changed template text')
        source, = (original / 'sources/canary-calls-all').glob('*.jsonl.gz')
        for line in gzip.open(source, 'rt'):
            call = json.loads(line)
            if call['call_id'] != error['call_id']:
                continue
            history = [normalize_message(x) for x in call['provider_payload']['messages']]
            response = normalize_message(call['assistant_response'])
            options = dict(tools=call['provider_payload'].get('tools'), enable_thinking=True)
            prefix = tokenizer.apply_chat_template(history, tokenize=False, add_generation_prompt=True, **options)
            rendered = tokenizer.apply_chat_template(history + [response], tokenize=False, add_generation_prompt=False, **options)
            assert rendered.startswith(prefix)
            suffix = rendered[len(prefix):]
            pids = tokenizer.encode(prefix, add_special_tokens=False)
            sids = tokenizer.encode(suffix, add_special_tokens=False)
            native = tokenizer.apply_chat_template(history, tokenize=True, return_dict=False, add_generation_prompt=True, **options)
            whole = decode(pids + sids)
            normalized = tokenizer.backend_tokenizer.normalizer.normalize_str(rendered)
            rows.append(dict(trial_id=ident, call_id=call['call_id'], source_export_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                original_affected_targets=len(report['errors']), actual_native_deployment_prefix_identical=pids == native,
                decoded_prefix_identical_to_rendered=decode(pids) == prefix,
                decoded_target_identical_to_rendered=decode(sids) == suffix,
                combined_decode_identical_to_native_prefix_decode_plus_original_target=whole == decode(pids) + suffix,
                combined_decode_identical_to_official_normalizer=whole == normalized,
                original_full_render_roundtrip=whole == rendered,
                prefix_nfc_changes=tokenizer.backend_tokenizer.normalizer.normalize_str(prefix) != prefix,
                suffix_nfc_changes=tokenizer.backend_tokenizer.normalizer.normalize_str(suffix) != suffix,
                rendered_surrogate_count=sum(0xD800 <= ord(c) <= 0xDFFF for c in rendered),
                original_source_or_target_changes=0, target_tokens_rewritten=0))
            break
        else:
            raise ValueError('Original failed target not present')
        print(json.dumps(rows[-1]), flush=True)
    target = S / 'metadata-snapshots/TOKENIZER_BOUNDARY_DIAGNOSIS_R360.json'
    with target.open('x') as stream:
        json.dump(dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), rows=rows,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            tokenizer_normalizer=json.loads(tokenizer.backend_tokenizer.to_str())['normalizer'],
            diagnostic_only=True, qualifier_or_index_mutations=0, teacher_calls=0), stream, indent=2)


if __name__ == '__main__':
    main()
