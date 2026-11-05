"""Read native metric snapshots and export curves; no training state is modified."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
os.environ['MPLCONFIGDIR']=str(R/'cache/matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def render():
    output=R/'reports/training-curves';output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for tag,run,planned in [('NEW-M1','new-m1-cf416-128k-e5',200),('NEW-M2','new-m2-tmax356-128k-e5',125)]:
        source=R/'runs'/run/'preflight-evidence-rank0.jsonl'
        if not source.exists():continue
        raw=source.read_bytes();events=[]
        for line in raw.splitlines():
            try:
                event=json.loads(line)
                if event.get('event')=='metrics':events.append(event)
            except json.JSONDecodeError:continue
        train={e['global_step']:e['metrics']for e in events if 'loss'in e['metrics']}
        validation={e['global_step']:e['metrics']for e in events if 'eval_loss'in e['metrics']}
        if not train:continue
        buffer=io.StringIO();writer=csv.writer(buffer)
        writer.writerow(['optimizer_step','train_loss','unique_row_validation_loss','grad_norm_before_clip','learning_rate','epoch','input_tokens_seen'])
        for step in sorted(set(train)|set(validation)):
            m=train.get(step,{});v=validation.get(step,{})
            writer.writerow([step,m.get('loss'),v.get('eval_loss'),m.get('grad_norm'),m.get('learning_rate'),m.get('epoch',v.get('epoch')),m.get('num_input_tokens_seen')])
        csv_file=output/(tag+'-metrics.csv');csv_file.write_text(buffer.getvalue())
        steps=sorted(train)
        fig,axes=plt.subplots(3,1,figsize=(9,7.5),sharex=True,layout='constrained')
        axes[0].plot(steps,[train[s]['loss']for s in steps],'.-',label='Train update mean',linewidth=1,markersize=3)
        if validation:
            vs=sorted(validation);axes[0].plot(vs,[validation[s]['eval_loss']for s in vs],'s',label='Validation: unique row mean',markersize=5)
        axes[0].set_ylabel('Loss');axes[0].set_ylim(bottom=0);axes[0].legend(fontsize=8)
        axes[1].plot(steps,[train[s]['learning_rate']for s in steps],color='#247b65')
        axes[1].set_ylabel('Learning rate');axes[1].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
        axes[2].plot(steps,[train[s].get('grad_norm',float('nan'))for s in steps],color='#8051a3')
        axes[2].set_ylabel('Gradient norm\n(before clip)');axes[2].set_xlabel('Actual optimizer step')
        for ax in axes:ax.grid(alpha=.2)
        fig.suptitle(tag+' on node18 | 128K, DP4, GA8 | observed '+str(steps[-1])+'/'+str(planned)+' steps')
        for extension in ['png','svg']:
            p=output/(tag+'-curves.'+extension);tmp=p.with_name(p.name+'.tmp')
            fig.savefig(tmp,format=extension,dpi=140);tmp.replace(p)
        plt.close(fig)
        manifest.append(dict(stage=tag,observed_optimizer_step=steps[-1],planned_optimizer_steps=planned,
            source=str(source),source_snapshot_sha256=hashlib.sha256(raw).hexdigest(),
            csv_sha256=hashlib.sha256(csv_file.read_bytes()).hexdigest(),
            png_sha256=hashlib.sha256((output/(tag+'-curves.png')).read_bytes()).hexdigest(),
            validation_rows_are_not_training_exposures=True))
    proof=dict(at=time.time(),read_only_native_metric_rendering=True,curves=manifest,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    p=output/'CURVE_MANIFEST.json';tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(proof,indent=2)+'\n');tmp.replace(p)
    print(json.dumps(proof))


if __name__=='__main__':render()
