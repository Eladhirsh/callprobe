"""Collect offline diagnostics for completed observations, without rescoring."""
import json
from pathlib import Path
from callprobe.models import Run
from callprobe.loader import load_suite
from callprobe.explain import explain_run
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
suites={v:load_suite(str(root/v)) for v in ('nested','flat')}
report=[]
for entry in manifest['runs']:
    if entry['status']=='running' or not (root/entry['file']).exists(): continue
    run=Run.model_validate_json((root/entry['file']).read_text())
    diagnostics=explain_run(run,suites[entry['variant']])
    report.append({'model':entry['model'],'variant':entry['variant'],
        'diagnostic_counts':diagnostics['diagnostic_counts'],
        'argument_shape_summary':diagnostics['argument_shape_summary'],
        'failures':[{'task':c['task_id'],'pad':c['pad'],'diagnostics':c['diagnostics']} for c in diagnostics['cases']]})
(root/'failure-patterns.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'Saved diagnostics for {len(report)} completed blocks')
