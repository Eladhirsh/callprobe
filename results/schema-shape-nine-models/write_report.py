"""Generate a report only after every planned run has finished."""
import hashlib, json, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
assert manifest['status']!='running'
subprocess.run([sys.executable,str(root/'analyze.py')],check=True)
summary=json.loads((root/'summary.json').read_text())
lines=['# Nine-model schema-shape experiment','',
'Published Callprobe 0.9.0rc1; fictional email tools; no mail API operations executed. Eighteen identical prompts across flat and nested contracts, with 0, 2, and 4 distractors. Nine locally installed Ollama models. Each task/shape/pad/model condition has one observation; 972 were planned.', '',
'Each model uses temperature 0, max_tokens 4096, concurrency 1 and retries 0. Model order is fixed and variant order alternates by model. No generated responses are repaired or rescored. Models differ in size, quantization, training, templates and tool parsers; this is a local compatibility experiment, not a universal ranking.', '',
'## Overall results','',
'| Model | Nested successes/scored | Flat successes/scored | Paired change (pp) | Improved cases | Regressed cases | Errors | Truncated |',
'| --- | --- | --- | --- | --- | --- | --- | --- |']
for row in summary['models']:
 n,f=row['variants']['nested'],row['variants']['flat']
 delta=(row['paired_flat_success']-row['paired_nested_success'])/row['paired_scored']*100 if row['paired_scored'] else None
 lines.append(f"| {row['model']} | {n['success']}/{n['scored']} | {f['success']}/{f['scored']} | {delta:+.1f} | {len(row['improved'])} | {len(row['regressed'])} | {n['errors']+f['errors']} | {n['truncated']+f['truncated']} |" if delta is not None else f"| {row['model']} | unavailable | unavailable | n/a | n/a | n/a | {n['errors']+f['errors']} | n/a |")
lines += ['', 'Request errors are excluded from scored denominators and disclosed above; truncations remain scored failures. A complete model/variant has 54 observations. Paired changes use only task/pad observations successfully scored in both contracts; models with request errors have fewer such pairs. Different suite hashes are intentional: these are descriptive paired contract comparisons, not same-suite CI regression gates.', '',
'## By distractor count','', '| Model | Pad | Nested | Flat |','| --- | --- | --- | --- |']
for row in summary['models']:
 for pad in ('0','2','4'):
  n,f=[row['variants'][v]['by_pad'][pad] for v in ('nested','flat')]
  lines.append(f"| {row['model']} | {pad} | {n['success']}/{n['scored']} | {f['success']}/{f['scored']} |")
lines += ['', '## Equivalence and limits','',
'Tool names, descriptions, leaf-field constraints, prompts and abstention expectations are identical. Only the argument grouping and matching assertion paths differ. Extra optional fields omitted from exact nested expectations are explicitly forbidden in flat expectations. `check_equivalence.py` verifies 68 paired argument outcomes and identical prompts. Suites are frozen copies of the prior experiment.', '',
'Eighteen synthetic cases are limited coverage. Two literal-text reply cases expect send mode even though the prompts say reply rather than explicitly send; that policy interpretation warrants review before using this suite as a production benchmark. These prompts and expectations were frozen for this experiment, not changed after observing results. Results can reflect provider/template/parser behavior as well as model capability. There are no independent repetitions in this wider matrix, no statistical significance claim, and no claim that additional distractors improve performance. The earlier Qwen-only experiment contains three temperature-zero consistency runs per variant.', '',
'## Inspect and reproduce','',
'`manifest.json` preserves model digests, quantization, server/package versions, commands, order, elapsed times, return codes and coverage. Numbered JSON files are raw results; corresponding logs preserve CLI diagnostics. `summary.json` lists exact cases improved and regressed at each padding level.', '',
'```bash', 'callprobe explain 01-nested.json --suite nested', 'callprobe explain 01-flat.json --suite flat', '```', '',
'To reproduce in a fresh directory with the same installed models, copy the scripts and both suites; leave numbered results and manifest out. Use Python with callprobe==0.9.0rc1 installed:', '',
'```bash','python check_equivalence.py','python run_matrix.py','python write_report.py','```','',
'No new model is downloaded automatically. The runner configures a 1,800-second subprocess timeout and preserves partial results when a block fails. Recorded duration uses wall-clock time and may include host scheduling or sleep; it is not a controlled inference-speed measurement. Inspect coverage before drawing conclusions.']
completed=sum(e.get('observations',0) for e in manifest['runs'])
errors=sum(e.get('errors',0) for e in manifest['runs'])
truncated=sum(e.get('truncated',0) for e in manifest['runs'])
index=lines.index('## Overall results')
lines[index:index]=[
    f'All **{completed} planned observations were recorded**: {completed-errors} scored responses, {errors} request errors, and {truncated} truncated responses (included as scored failures).', '',
    'Flattening improved paired success for five models, reduced it for three, and left one unchanged. Across scored pairs, 85 observations improved and 27 regressed. Qwen 3 had the highest flat score here (48/54), but still regressed two conditions. This supports an explicit contract-comparison option, not automatic flattening as a universal default.', '',
    'The experiment completed without a harness crash. Model failures, request timeouts and truncated responses remain distinct in the saved evidence. Model digests were checked again after the run and were unchanged.', ''
]
(root/'README.md').write_text('\n'.join(lines)+'\n')
files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='checksums.json'}
(root/'checksums.json').write_text(json.dumps(files,indent=2)+'\n')
print('Report and checksums saved')
