import os,sys,json
from pathlib import Path
from sft.runtime.config import validate_native,native_arguments
from sft.runtime.canary import prepare_capacity772
from llamafactory.hparams import get_train_args
import yaml
W=Path('/ssd/chenkeyi/qwen35-sft-772-20261101/new-sft/workspace')
cfg=yaml.safe_load((W/"configs/capacity-template.yaml").read_text())
validate_native(cfg,bounded=True)
get_train_args(native_arguments(cfg)|dict(use_cpu=True,bf16=False,do_train=False,do_eval=False,deepspeed=None))
print(json.dumps(prepare_capacity772('/ssd/chenkeyi/qwen35-sft-772-20261101/assets/source17-r1/new-corpus-r426',262144,8)),flush=True)
