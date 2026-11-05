"""Freeze outcome-blind family splits, TB-referenced quotas and reserve orders.

Run after inventory_public_tasks.py on the sole controller. This is source
analysis, not a Harbor scheduler. No result, trajectory, reward or old solution
is read. Native difficulty labels remain distinct across datasets.
"""
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import re

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
MAPPING = {
    'software-engineering': 'software', 'debugging': 'software',
    'system-administration': 'systems', 'file-operations': 'files',
    'data-processing': 'data', 'data-querying': 'data',
    'data-science': 'data-science-ml', 'machine-learning': 'data-science-ml',
    'model-training': 'data-science-ml', 'scientific-computing': 'science-math',
    'mathematics': 'science-math', 'optimization': 'science-math',
    'security': 'security', 'games': 'interactive',
    'personal-assistant': 'interactive', 'video-processing': 'media',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def grams(text, template=False):
    if template:
        text = re.sub(r'`[^`]+`|\b0x[0-9a-f]+\b|\b\d+(?:\.\d+)?\b', ' VALUE ', text, flags=re.I)
    words = re.findall(r'[a-z0-9_]+', text.lower())
    return {hashlib.sha256(' '.join(words[i:i+5]).encode()).digest()[:12]
            for i in range(max(0, len(words)-4))}


def allocate(n, weights, capacities=None, minimum=False):
    """Capped largest remainders, deterministic ties; never silently lose seats."""
    keys = sorted(k for k, v in weights.items() if v > 0 and (capacities is None or capacities.get(k, 0) > 0))
    caps = {k: (n if capacities is None else capacities[k]) for k in keys}
    if sum(caps.values()) < n:
        raise ValueError('Stratum has insufficient capacity for its preregistered quota')
    result = {k: 0 for k in keys}
    if minimum and n >= len(keys):
        result = {k: 1 for k in keys}
    while sum(result.values()) < n:
        active = [k for k in keys if result[k] < caps[k]]
        remaining = n - sum(result.values())
        total = sum(weights[k] for k in active)
        desired = {k: remaining * weights[k] / total for k in active}
        increments = {k: min(caps[k]-result[k], math.floor(desired[k])) for k in active}
        for k, increment in increments.items():
            result[k] += increment
        remaining = n - sum(result.values())
        active = [k for k in active if result[k] < caps[k]]
        for k in sorted(active, key=lambda k: (-(desired[k] - math.floor(desired[k])), k))[:remaining]:
            result[k] += 1
    return result


class Families:
    def __init__(self, count):
        self.parents = list(range(count))

    def find(self, index):
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def join(self, left, right):
        left, right = self.find(left), self.find(right)
        self.parents[max(left, right)] = min(left, right)


def distribution(rows):
    keys = ['coarse_category', 'native_category', 'native_difficulty', 'subset', 'skill_type', 'split']
    result = {key: dict(sorted(Counter(str(r.get(key, 'NOT_PUBLISHED')) for r in rows).items())) for key in keys}
    result['unique_tasks'] = len(rows)
    result['families'] = len({r.get('family_id') for r in rows})
    result['skills'] = dict(sorted(Counter(s for r in rows for s in r['skills']).items()))
    return result


def save(name, value, lines=False):
    target = ROOT / 'manifests' / name
    with target.open('x') as stream:
        if lines:
            for row in value:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    return dict(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def main():
    refs = list(map(json.loads, (ROOT / 'sources/tb21-public-reference.jsonl').open()))
    if len(refs) != 89 or len({r['task_id'] for r in refs}) != 89:
        raise ValueError('TB reference changed')
    reference_counts = Counter(MAPPING[r['public_metadata']['category']] for r in refs)
    pool = []
    for filename in ['calibforge-public-metadata.jsonl', 'tmax-public-metadata.jsonl']:
        for source in map(json.loads, (ROOT / 'sources' / filename).open()):
            cf = source['dataset'] == 'AweAI-Team/CalibForge'
            native = source['category'] if cf else source['domain'].replace('_', '-')
            pool.append(dict(source, pool='calibforge' if cf else 'tmax',
                native_category=native, coarse_category=MAPPING.get(native, 'UNMATCHED'),
                native_difficulty=source['difficulty'] if cf else source['task_complexity'],
                skills=source['tags'] if cf else [source['skill_type']] + source['primitive_skills']))
    pool.sort(key=lambda r: (r['pool'], r['task_id']))
    family = Families(len(pool))
    owners = {}
    exclusions = defaultdict(list)
    evidence = []
    refgrams = [grams(r['instruction']) for r in refs]
    reftemplates = [grams(r['instruction'], True) for r in refs]
    refexact = {digest(re.findall(r'[a-z0-9_]+', r['instruction'].lower())): r['task_id'] for r in refs}
    refnames = re.compile(r'(?<![a-z0-9_-])(?:' + '|'.join(re.escape(r['task_id']) for r in refs) + r')(?![a-z0-9_-])', re.I)
    private_hashes = {f['sha256']: r['task_id'] for r in refs for f in r['private_file_identities']
                      if f['path'].endswith('.py')}
    cfindex = defaultdict(list)
    cfgrams = {}
    for index, row in enumerate(pool):
        groupkey = ((row['pool'], re.sub(r'_\d+$', '', row['task_id'])) if row['pool'] == 'calibforge'
                    else (row['pool'], row['domain'], row['skill_type'], row['scenario']))
        template = grams(row['instruction'], True)
        keys = [('generation_family', groupkey), ('prompt_template', digest(sorted(g.hex() for g in template)))]
        bundle = sorted(f['sha256'] for f in row['private_file_identities'] if f['path'].endswith('.py'))
        if bundle:
            keys.append(('verifier_bundle', row['pool'], digest(bundle)))
        for key in keys:
            if key in owners:
                family.join(index, owners[key])
                prior = owners[key]
                if key[0] == 'prompt_template' and row['pool'] != pool[prior]['pool']:
                    exclusions[index].append('CROSS_POOL_EXACT_NORMALIZED_TEMPLATE')
                    exclusions[prior].append('CROSS_POOL_EXACT_NORMALIZED_TEMPLATE')
                    evidence.append(dict(kind='CROSS_POOL_EXACT_NORMALIZED_TEMPLATE', tasks=[pool[prior]['task_id'], row['task_id']]))
            else:
                owners[key] = index
        exact = digest(re.findall(r'[a-z0-9_]+', row['instruction'].lower()))
        exactkey = ('exact_instruction', exact)
        if exactkey in owners:
            prior = owners[exactkey]
            family.join(index, prior)
            # Symmetric cross-pool removal; deterministic first representative within a pool.
            exclusions[index].append('EXACT_DUPLICATE')
            if pool[prior]['pool'] != row['pool']:
                exclusions[prior].append('CROSS_POOL_EXACT_DUPLICATE')
            evidence.append(dict(kind='EXACT_DUPLICATE', tasks=[pool[prior]['task_id'], row['task_id']]))
        else:
            owners[exactkey] = index
        current = grams(row['instruction'])
        if exact in refexact:
            exclusions[index].append('TB21_EXACT_INSTRUCTION')
            evidence.append(dict(kind='TB21_EXACT_INSTRUCTION', task=row['task_id'], reference=refexact[exact]))
        mentions = sorted(set(refnames.findall(row['instruction'] + '\n' + row['environment_definition'])))
        if mentions:
            exclusions[index].append('TB21_NAMED_SOURCE_OR_TEMPLATE')
            evidence.append(dict(kind='TB21_NAMED_SOURCE_OR_TEMPLATE', task=row['task_id'], references=mentions))
        for ref, other in zip(refs, refgrams):
            intersection = len(current & other)
            union = len(current | other)
            jaccard = intersection / union if union else 0
            containment = intersection / min(len(current), len(other)) if min(len(current), len(other)) else 0
            if jaccard >= .30 or (intersection >= 20 and containment >= .60):
                exclusions[index].append('TB21_NEAR_INSTRUCTION')
                evidence.append(dict(kind='TB21_NEAR_INSTRUCTION', task=row['task_id'], reference=ref['task_id'],
                    jaccard5=jaccard, containment5=containment, shared_shingles=intersection))
        for ref, other in zip(refs, reftemplates):
            intersection = len(template & other)
            union = len(template | other)
            jaccard = intersection / union if union else 0
            if intersection >= 20 and jaccard >= .65:
                exclusions[index].append('TB21_NORMALIZED_TEMPLATE_RISK')
                evidence.append(dict(kind='TB21_NORMALIZED_TEMPLATE_RISK', task=row['task_id'], reference=ref['task_id'],
                    template_jaccard5=jaccard, shared_shingles=intersection))
        shared = sorted({private_hashes[f['sha256']] for f in row['private_file_identities']
                         if f['sha256'] in private_hashes})
        if shared:
            exclusions[index].append('TB21_EXACT_VERIFIER_CODE')
            evidence.append(dict(kind='TB21_EXACT_VERIFIER_CODE', task=row['task_id'], references=shared))
        if row['pool'] == 'calibforge':
            cfgrams[index] = current
            for gram in current:
                cfindex[gram].append(index)
        else:
            # Ignore phrases shared by >200 CF tasks when generating candidates;
            # full exact sets are used to verify each candidate. This limit is audited.
            candidates = Counter(i for gram in current for i in cfindex.get(gram, ()) if len(cfindex[gram]) <= 200)
            for other_index, overlap in candidates.items():
                if overlap < 10:
                    continue
                other = cfgrams[other_index]
                intersection = len(current & other)
                jaccard = intersection / len(current | other) if current | other else 0
                containment = intersection / min(len(current), len(other)) if min(len(current), len(other)) else 0
                if jaccard >= .60 or (intersection >= 20 and containment >= .80):
                    family.join(index, other_index)
                    exclusions[index].append('CROSS_POOL_NEAR_OR_TEMPLATE_DUPLICATE')
                    exclusions[other_index].append('CROSS_POOL_NEAR_OR_TEMPLATE_DUPLICATE')
                    evidence.append(dict(kind='CROSS_POOL_NEAR_OR_TEMPLATE_DUPLICATE',
                        tasks=[pool[other_index]['task_id'], row['task_id']], jaccard5=jaccard, containment5=containment))
        if index % 1000 == 0:
            print(json.dumps(dict(event='screen_progress', tasks=index, total=len(pool))), flush=True)
    members = defaultdict(list)
    for index in range(len(pool)):
        members[family.find(index)].append(pool[index]['pool'] + ':' + pool[index]['task_id'])
    for index, row in enumerate(pool):
        row['family_id'] = 'family:' + digest(sorted(members[family.find(index)]))
        # Assigned to the full source universe before quota selection or any model attempt.
        row['split'] = 'validation' if int(digest(['42', row['family_id']])[:16], 16) % 10 == 0 else 'train'
        row['exclusion_reasons'] = sorted(set(exclusions[index]))
    mapping = dict(coarse_mapping=MAPPING, normalization='TMax domain underscore -> hyphen',
        reference_counts=dict(reference_counts), tb21_tasks=89,
        evidence_policy='Original public category and native skill labels only; no model outcomes read',
        tmax_skill_mapping={skill: dict(coarse_categories=sorted({r['coarse_category'] for r in pool if r.get('skill_type') == skill}),
            rule='Skill is a separate coverage axis; domain determines category, no forced skill/category equivalence')
            for skill in sorted({r['skill_type'] for r in pool if 'skill_type' in r})},
        difficulty_policy='Stratify original labels within each pool; CF easy/medium/hard and TMax workflow complexity are not equivalent',
        limitations=['Lexical/template screening is not a proof against every semantic rewrite.',
            'Source generation/scenario and identical verifier bundles conservatively define families; official author family IDs unavailable.',
            'Cross-pool candidate generation ignores shingles present in more than 200 CF tasks; threshold verified using full sets.'],
        unmapped_tasks=[r['task_id'] for r in pool if r['coarse_category'] == 'UNMATCHED'])
    files = dict(mapping=save('CATEGORY_MAPPING.json', mapping),
        reference=save('TB21_89_REFERENCE.jsonl', refs, True),
        decontamination=save('DECONTAMINATION_EVIDENCE.jsonl', evidence, True))
    summary = {}
    for name in ['calibforge', 'tmax']:
        original = [r for r in pool if r['pool'] == name]
        eligible = [r for r in original if not r['exclusion_reasons'] and r['coarse_category'] != 'UNMATCHED']
        groups = defaultdict(list)
        for row in eligible:
            leaf = (row['coarse_category'], row['split'], row.get('subset', 'main'),
                    row.get('skill_type', row['native_category']), row['native_difficulty'])
            groups[leaf].append(row)
        rng = random.Random(42)
        # Family round-robin within a leaf prevents a prolific generation batch
        # consuming it; the remaining deterministic order is the reserve list.
        for leaf, rows in groups.items():
            by_family = defaultdict(list)
            for row in sorted(rows, key=lambda r: r['task_id']):
                by_family[row['family_id']].append(row)
            identifiers = sorted(by_family)
            rng.shuffle(identifiers)
            for values in by_family.values():
                rng.shuffle(values)
            ordered = []
            while identifiers:
                for ident in identifiers:
                    ordered.append(by_family[ident].pop())
                identifiers = [ident for ident in identifiers if by_family[ident]]
            groups[leaf] = ordered
        supported = {r['coarse_category'] for r in eligible}
        weights = {k: v for k, v in reference_counts.items() if k in supported}
        selected, reserves, allocations = [], [], []
        for split, count in [('train', 450), ('validation', 50)]:
            capacities = Counter(r['coarse_category'] for r in eligible if r['split'] == split)
            top = allocate(count, weights, capacities)
            for category, seats in top.items():
                leaves = {leaf: len(rows) for leaf, rows in groups.items() if leaf[:2] == (category, split)}
                # Preserve native source/subset/skill/difficulty proportions and
                # cover all nonempty leaves when the category budget permits.
                quotas = allocate(seats, leaves, leaves, minimum=True)
                for leaf, quota in quotas.items():
                    for rank, row in enumerate(groups[leaf]):
                        public = {k: v for k, v in row.items() if k not in ('instruction', 'environment_definition', 'original_config')}
                        public.update(stratum=list(leaf), reserve_rank=rank, stratum_selected_count=quota,
                            preparation_status='PENDING', model_attempts=0, max_attempts=2)
                        (selected if rank < quota else reserves).append(public)
                    allocations.append(dict(stratum=list(leaf), quota=quota, available=leaves[leaf]))
        if len(selected) != 500 or len({r['task_id'] for r in selected}) != 500:
            raise ValueError('Each selected pool must have 500 unique original tasks')
        # Canary order is diverse and deterministic; selected membership is fixed.
        selected.sort(key=lambda r: digest([42, r['pool'], r['task_id']]))
        canary, seen = [], set()
        for row in selected:
            key = (row['coarse_category'], row.get('subset', 'main'))
            if key not in seen and len(canary) < 8:
                canary.append(row['task_id']); seen.add(key)
        canary += [r['task_id'] for r in selected if r['task_id'] not in canary][:8-len(canary)]
        summary[name] = dict(original=distribution(original), eligible=distribution(eligible), selected=distribution(selected),
            successful=None, missing_reference_categories=sorted(set(reference_counts)-supported),
            native_label_coverage_is_not_distribution_equivalence=True,
            exclusion_counts=dict(Counter(reason for r in original for reason in r['exclusion_reasons'])),
            canary_task_ids=canary, selected_manifest=save(name.upper() + '_500_TASKS.jsonl', selected, True),
            reserve_manifest=save(name.upper() + '_RESERVES.jsonl', reserves, True),
            allocation_manifest=save(name.upper() + '_STRATA.json', allocations))
    manifest = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), seed=42,
        status='SAMPLING_FROZEN_ENVIRONMENT_PREPARATION_PENDING', files=files, pools=summary,
        task_family_split='Full source universe first; hash(seed,family) modulo 10, then fixed 450/50 sample quotas',
        category_sampling='TB89 coarse proportions renormalized over supported categories; capped largest remainders',
        replacement_policy='Only pre-model non-runnable tasks, next reserve in the exact same stratum; immutable replacement ledger required',
        post_attempt_replacement_allowed=False, model_outcomes_used=False, attempts_cap=2000,
        original_sources_unchanged=True, old_sft_or_solution_trajectories_used=False)
    files['family_splits'] = save('SOURCE_FAMILY_SPLITS.jsonl', [dict(pool=r['pool'], task_id=r['task_id'], family_id=r['family_id'],
        split=r['split'], exclusion_reasons=r['exclusion_reasons']) for r in pool], True)
    manifest['input_inventory'] = dict(path=str(ROOT / 'checks/public-source-inventory.json'),
        sha256=hashlib.sha256((ROOT / 'checks/public-source-inventory.json').read_bytes()).hexdigest())
    manifest['sampling_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save('SAMPLING_MANIFEST.json', manifest)
    print(json.dumps(dict(event='sampling_frozen', pools={k: dict(tasks=v['selected']['unique_tasks'],
        split=v['selected']['split'], coarse=v['selected']['coarse_category'], canary=v['canary_task_ids'])
        for k, v in summary.items()})), flush=True)


if __name__ == '__main__':
    main()
