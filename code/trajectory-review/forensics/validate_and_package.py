"""Validate the offline evidence view and package it; no production writes."""
import base64
import gzip
import hashlib
import json
import re
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'report'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text())
manifest=load(OUT/'AUDIT_MANIFEST.json')
entries=manifest['entries'];byid={e['id']:e for e in entries}
assert len(entries)==58 and len(byid)==58
snapshot=load(ROOT/'private/SOURCE_AND_STATUS_SNAPSHOT_R1.json')
source_results={r['id']:r for r in snapshot['rows']}
rows=[];credential_hits=0

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.remote_resources=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a'and a.get('href'):self.links.append(a['href'])
        if tag in ['script','img','iframe','link']:
            s=a.get('src')or a.get('href')
            if s:self.remote_resources.append(s)

for e in entries:
    original=(ROOT/'private'/e['derived_evidence_file']).read_bytes()
    assert sha(original)==e['derived_evidence_sha256']
    d=json.loads(gzip.decompress(original))
    page=OUT/e['html_file'];h=page.read_text()
    packed=re.search(r'<script id="packed-data"[^>]*>([^<]+)</script>',h).group(1)
    decoded=json.loads(gzip.decompress(base64.b64decode(packed)))
    rendered=decoded['trajectory'];rendered.pop('bounded_wire_evidence',None)
    assert rendered==d,(e['id'],'view changed source content')
    assert e['calls']==len(d['calls']) and e['tools']==len(d['tools'])
    assert decoded['notes']['finding']==e['finding']
    for t in decoded['notes']['key_tools']:assert 0<t<=len(d['tools'])
    if e['label']!='OLD_M0':
        assert source_results[e['id']]['sha256']==e['original_result_sha256']
    raw=json.dumps(d,ensure_ascii=False)
    credential_hits+=len(re.findall(r'(?i)(?:https?|socks5h?)://[^/\s:@]+:[^/@\s]+@',raw))
    rows.append(dict(id=e['id'],embedded_source_equal=True,counts_equal=True,sha256=sha(page.read_bytes())))

links=0
for p in OUT.rglob('*.html'):
    parser=Links();parser.feed(p.read_text());assert not parser.remote_resources,(p,parser.remote_resources)
    for href in parser.links:
        if href.startswith('#'):continue
        assert '://'not in href,(p,href)
        name,_,anchor=href.partition('#');target=(p.parent/name).resolve()
        assert target.is_file(),(p,href)
        if anchor.startswith('tool-'):
            uid=target.stem;assert uid in byid and 0<int(anchor[5:])<=byid[uid]['tools']
        links+=1

s=manifest['summary']
assert s['calls']==19080 and s['tools']==19012
assert s['exact_parsed_call_to_tool_start']==s['compared_parsed_call_to_tool_start']==19012
assert s['zero_call_current_sft']==10
assert s['length_call_sources']=={'agent':10,'compaction':9}
assert s['execution_counts']['Agent 正常闭合']==5
assert s['execution_counts']['模型传输中断']==4
assert s['execution_counts']['Agent 10800 秒超时']==27
assert s['scoring_counts']['Verifier 未启动 / UNKNOWN']==8
assert len(manifest['old_success_retention'])==14
assert len(load(OUT/'SSE_TOOL_COMPARISON.json'))==4
assert credential_hits==0,('possible credentialed URL; inspect locally before sharing',credential_hits)

readme='''打开 index.html 查看总表，m0-comparison.html 为两个 M0 案例的静态对照。
请先完整解压，保留 episodes 目录；用近期 Chrome、Edge 或 Firefox 打开。
每个单轨迹 HTML 独立内嵌 gzip 数据，可离线打开，不需要服务端、网络或模型。
上方结论与官方日志是静态内容；逐回合查看需要浏览器支持 DecompressionStream。

本交付是历史证据分析，不是重新评测或修订历史分数。
58条：2旧M0、2新M0、54条训练Checkpoint终态。
完整Provider请求只在M0两个案例新旧对照中导出，其余为最后6条真实消息+完整请求哈希。
原始SSE只额外提取4个关键Call，Serving Parser前生成Token未冒充齐全。
大字段若有显示限制会显式标识；原始Recorder留在原节点，不在此包中伪造补全。
官方测试只供受信任审阅，不用于Agent输入。
TRAJECTORY_AUDIT.md提供逐条中文结论、证据、归因边界和可证伪对照。
AUDIT_MANIFEST.json、TRAJECTORY_INDEX.csv与SHA256SUMS.txt提供映射及校验。
VIEWER_DOM_SMOKE.json为真实gzip解码/导航的DOM模拟验收，不宣称完成真浏览器视觉测试。
'''
(OUT/'README.txt').write_text(readme)
provenance=[]
for p in sorted((ROOT/'scripts').glob('*')):
    if p.is_file():provenance.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p.read_bytes())))
(OUT/'CODE_PROVENANCE.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
validation=dict(at=time.time(),trajectory_pages=len(rows),validated_relative_links=links,all_embedded_trajectories_equal_collected_evidence=True,
    current_results_match_frozen_snapshot=True,no_remote_page_resources=True,potential_credentialed_urls=credential_hits,
    tests=rows,scope='Source/HTML integrity and navigation smoke. Not full native Recorder reference-graph certification or visual-browser validation.')
(OUT/'VIEWER_INTEGRITY_VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
checks=[]
for p in sorted(OUT.rglob('*')):
    if p.is_file()and p.name!='SHA256SUMS.txt':checks.append(sha(p.read_bytes())+'  '+str(p.relative_to(OUT)))
(OUT/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
archive=ROOT/'TRAJECTORY_REVIEW_58_20261105.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():z.write(p,arcname=str(p.relative_to(OUT)))
with zipfile.ZipFile(archive)as z:assert z.testzip()is None
archive_sha=sha(archive.read_bytes());(ROOT/(archive.name+'.sha256')).write_text(archive_sha+'  '+archive.name+'\n')
print(json.dumps(dict(pages=len(rows),links=links,archive=str(archive),bytes=archive.stat().st_size,sha256=archive_sha),ensure_ascii=False))
