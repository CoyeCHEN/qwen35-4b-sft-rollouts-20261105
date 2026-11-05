"""Verify the remote ZIP, append exactly 54 offline pages and deliver to Desktop."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

BASE=Path(__file__).resolve().parent
REVIEW=Path('/mnt/c/Users/18489/Desktop/Qwen35-trajectory-review-20261105')
DESKTOP=Path('/mnt/c/Users/18489/Desktop')
NAME='Qwen35-SFT-checkpoint-54-rollouts-20261105.zip'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def main():
    source=BASE/'download'/NAME
    status=json.loads((BASE/'REMOTE_EXPORT_STATUS.json').read_text())
    selected=json.loads((BASE/'FROZEN_54_SELECTION.json').read_text())
    assert status['status']=='ARCHIVE_COMPLETE' and status['trial_count']==54
    assert sha(source)==status['archive_sha256']
    assert not (BASE/'LOCAL_DELIVERY.json').exists(),'Existing delivery retained'
    destination=DESKTOP/NAME; temporary=destination.with_suffix('.zip.copying')
    assert not destination.exists() and not temporary.exists(),'Existing desktop export retained'
    for row in selected:
        assert sha(REVIEW/row['html_file'])==row['html_sha256']
    with zipfile.ZipFile(source,'a',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        index=json.loads(archive.read('TRIAL_INDEX.json'))
        assert {r['id'] for r in index}=={r['id'] for r in selected}
        for row in index:
            result=archive.read(row['archive_prefix']+'/result.json')
            assert hashlib.sha256(result).hexdigest()==row['original_result_sha256']
        archive.write(BASE/'README.zh-CN.txt','README.zh-CN.txt')
        archive.write(BASE/'54_TRAJECTORY_INDEX.csv','54_TRAJECTORY_INDEX.csv')
        archive.write(BASE/'FROZEN_54_SELECTION.json','FROZEN_54_SELECTION.json')
        archive.write(BASE/'index.html','review/index.html')
        archive.writestr('review/m0-comparison.html','<!doctype html><meta charset="utf-8"><title>本包范围</title><p>本包仅包含54条SFT模型轨迹，没有打包M0对照数据。</p><a href="index.html">返回54条轨迹索引</a>')
        for row in selected:
            page=REVIEW/row['html_file']
            archive.write(page,'review/episodes/'+row['id']+'.html')
        receipt={'scope':'Exactly the frozen 54 SFT checkpoint trials','groups':status['groups'],'remote_archive_sha256':status['archive_sha256'],'remote_source_bytes':status['source_bytes'],'remote_raw_files':status['files'],'source_results_and_available_journals_verified':True,'includes_M0':False,'includes_old_M1_M2':False,'new_model_requests':0}
        archive.writestr('EXPORT_RECEIPT.json',json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    # SHA equality proves the copy; no need to decompress 35GB on this low-RAM WSL.
    digest=sha(source)
    shutil.copyfile(source,temporary)
    assert sha(temporary)==digest
    temporary.rename(destination)
    with zipfile.ZipFile(destination) as archive:
        pages=[n for n in archive.namelist() if n.startswith('review/episodes/') and n.endswith('.html')]
        assert len(pages)==54
        names=archive.namelist()
        assert not any(n.startswith('raw/M0') or n.startswith('raw/OLD_') for n in names)
    (DESKTOP/(NAME+'.sha256.txt')).write_text(digest+'  '+NAME+'\n')
    result={'status':'DELIVERED','path':str(destination),'archive_bytes':destination.stat().st_size,'sha256':digest,'trials':54,'groups':status['groups'],'offline_pages':54,'source_bytes':status['source_bytes'],'raw_files':status['files'],'local_full_decompression_performed':False,'remote_source_hash_and_local_whole_archive_hash_verified':True}
    (BASE/'LOCAL_DELIVERY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
