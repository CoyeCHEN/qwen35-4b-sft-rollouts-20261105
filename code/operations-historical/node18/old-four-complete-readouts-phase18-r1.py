"""Existing unique advance leaf: original four training,14 NLL readouts and112 behavior Trials."""
import importlib
from pathlib import Path
core=importlib.import_module('old-four-after-selected267-phase18-r2')
nll=importlib.import_module('old443-phase-readouts18-r3')
behavior=importlib.import_module('old112-phase18-r2')
compare=importlib.import_module('compare-old-four-readonly18-r2')
transport=importlib.import_module('phase_progression18_r14')
R=core.R;P=core.P;C=core.C;read=core.read;sha=core.sha

def advance(owner,state):
 core.advance(owner,state)
 gate=state.get('old_four_after_selected267_gate',{})
 if not gate.get('passed')or not(R/'checks/SELECTED267_IDLE_SGL_SERVICES_RELEASED_R1.json').exists():return
 # GPU0..3 use the unchanged native trainer; NLL usesGPU5 and behavior usesGPU4.
 # Each existing entry independently refuses occupied GPUs and preserves healthy owners.
 for name,action in [('old443',lambda:nll.advance(state)),('old112',lambda:behavior.advance(owner,state,transport.remote,transport.request)),('old_comparison',compare.main)]:
  try:action()
  except Exception as error:state[name+'_readout_blocker']=repr(error)
 path=P/'checks/OLD_FOUR_UNIFIED_COMPARISON_R2.json'
 if path.exists():
  proof=read(path);state['old_four_readout_summary']=dict(complete=proof['complete'],nll_models=proof['complete443_readout_models'],behavior_terminal=proof['terminal_behavior_trials'],comparison_path=str(path),comparison_sha256=sha(path))
  if proof['complete']:state['status']='OLD_FOUR_NATIVE_TRAINING_AND14_NLL_AND112_BEHAVIOR_COMPLETE'
