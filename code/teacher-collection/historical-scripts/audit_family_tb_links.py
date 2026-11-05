"""Review selected siblings of TB-flagged sources using public task evidence only.

Generation batch/scenario groups are deliberately broader than duplicate
templates. A shared group is reported separately from a matched template/test.
No teacher result, failure list, reward or trajectory is read.
"""
from collections import defaultdict
import hashlib
import json

from sample_task_pools import ROOT,grams


def overlap(a,b):
    return len(a&b)/len(a|b) if a|b else 0


def main():
    source={}
    for name in ['calibforge-public-metadata.jsonl','tmax-public-metadata.jsonl']:
        for row in map(json.loads,(ROOT/'sources'/name).open()):source[row['task_id']]=row
    flagged=defaultdict(list)
    for row in map(json.loads,(ROOT/'manifests/SOURCE_FAMILY_SPLITS.jsonl').open()):
        if any(s.startswith('TB21_') for s in row['exclusion_reasons']):flagged[row['family_id']].append(row)
    records=[]
    for pool,filename in [('calibforge','CALIBFORGE_500_TASKS.jsonl'),('tmax','TMAX_RUNTIME_CANDIDATES_V2.jsonl')]:
        for selected in map(json.loads,(ROOT/'manifests'/filename).open()):
            comparisons=[];row=source[selected['task_id']]
            for sibling in flagged[selected['family_id']]:
                other=source[sibling['task_id']]
                def bundle(x):return sorted(f['sha256'] for f in x['private_file_identities'] if f['path'].endswith('.py'))
                raw=overlap(grams(row['instruction']),grams(other['instruction']))
                template=overlap(grams(row['instruction'],True),grams(other['instruction'],True))
                same_tests=bool(bundle(row)) and bundle(row)==bundle(other)
                comparisons.append(dict(sibling_task_id=sibling['task_id'],sibling_exclusion_reasons=sibling['exclusion_reasons'],
                    instruction_jaccard5=raw,normalized_template_jaccard5=template,identical_verifier_bundle=same_tests,
                    high_risk_template_or_verifier_link=raw>=.6 or template>=.65 or same_tests,
                    sibling_instruction_sha256=hashlib.sha256(other['instruction'].encode()).hexdigest()))
            if comparisons:
                records.append(dict(pool=pool,task_id=row['task_id'],family_id=selected['family_id'],
                    selected_instruction_sha256=hashlib.sha256(row['instruction'].encode()).hexdigest(),
                    comparisons=comparisons,high_risk=any(x['high_risk_template_or_verifier_link'] for x in comparisons),
                    shared_group_basis='CF generation batch or TMax domain/skill/scenario; conservative split grouping'))
    report=dict(status='PUBLIC_FAMILY_LINK_SCREEN_COMPLETE',records=records,
        selected_with_broad_tb_flagged_family_link=len(records),high_risk_selected=[x['task_id'] for x in records if x['high_risk']],
        model_outcomes_or_trajectories_read=False,
        interpretation='Shared batch/scenario alone does not establish a duplicate. Instruction/template and original verifier links are listed separately.',
        limitation='Lexical/structural review is not proof against every semantic rewrite')
    (ROOT/'checks/family-tb-source-links.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))
    print(json.dumps(sorted([(max(c['normalized_template_jaccard5'] for c in r['comparisons']),r['task_id']) for r in records],reverse=True)[:10]))


if __name__=='__main__':main()
