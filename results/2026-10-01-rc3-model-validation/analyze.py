"""Analyze frozen raw observations, export JUnit, and cross-check its counters.

Run with the installed development Python after run_validation.py completes:
  /path/to/python analyze.py /path/to/output
No network requests; raw result files are never modified or rescored.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter

from callprobe.explain import classify_case
from callprobe.loader import load_suite
from callprobe.models import Run


def main():
    root=Path(sys.argv[1]).resolve()
    experiments=json.loads((root/'experiment.json').read_text())
    if experiments['status']=='running':
        raise SystemExit('Experiment is still running; do not analyze a moving checkpoint')
    summary={'note':'Recorded outcomes, no rescoring. Separate suites; do not combine into a model ranking.',
             'models_unchanged':experiments['models_unchanged'], 'suites':{},'junit_checks':[]}
    for name in ('core','mail'):
        suite=load_suite(root/f'{name}-suite')
        tasks={t.id:t for t in suite.tasks}
        entries=[]
        manifest=json.loads((root/name/'manifest.json').read_text())
        for entry in manifest['models']:
            raw=entry.get('raw_result_file')
            if not raw:
                entries.append({'model':entry['model'],'status':entry['status'],'recorded':0})
                continue
            path=root/name/raw
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            run=Run.model_validate_json(path.read_text())
            assert run.config.suite_hash==suite.hash
            expected=len(run.config.task_ids)*len(run.config.pads)*run.config.repeats
            index={(r.task_id,r.pad,r.repeat):r for r in run.results}
            assert len(index)==len(run.results)
            repeat_pairs=[]
            if run.config.repeats==2:
                for task in tasks:
                    for pad in run.config.pads:
                        a,b=index.get((task,pad,0)),index.get((task,pad,1))
                        if a and b and a.error is None and b.error is None:
                            repeat_pairs.append({'task_id':task,'pad':pad,'first':a.success,'second':b.success})
            diagnostics=Counter()
            for result in run.results:
                if result.success and not result.truncated and result.error is None:
                    continue
                task=tasks[result.task_id]
                diagnostics.update(classify_case(task,suite.bundles[task.bundle],result))
            def counts(rows):
                good=[r for r in rows if r.error is None]
                return {'recorded':len(rows),'scored':len(good),'passed':sum(r.success for r in good),
                        'success':sum(r.success for r in good)/len(good) if good else None,
                        'errors':len(rows)-len(good),'truncated':sum(r.truncated for r in rows)}
            row={'model':run.config.model,'status':entry['status'],'planned':expected,
                 **counts(run.results),'failure_patterns':dict(diagnostics),
                 'by_pad':{str(p):counts([r for r in run.results if r.pad==p]) for p in run.config.pads},
                 'by_repeat':{str(i):counts([r for r in run.results if r.repeat==i]) for i in range(run.config.repeats)},
                 'repeat_pairs':len(repeat_pairs),
                 'repeat_disagreements':[p for p in repeat_pairs if p['first']!=p['second']],
                 'raw_sha256':before}
            xml=path.with_name(path.name.replace('-result.json','-junit.xml'))
            subprocess.run([sys.executable,'-m','callprobe.cli','report',str(path),'--format','junit','--out',str(xml),'--force'],check=True,capture_output=True)
            parsed=ET.parse(xml)
            expected_errors=sum(r.error is not None for r in run.results)+(len(run.results)<expected)
            expected_failures=sum(r.error is None and (not r.success or r.truncated) for r in run.results)
            assert len(parsed.findall('.//error'))==expected_errors
            assert len(parsed.findall('.//failure'))==expected_failures
            expected_cases=len(run.results)+(len(run.results)<expected)
            assert len(parsed.findall('.//testcase'))==expected_cases
            test_suite=parsed.find('testsuite')
            assert int(test_suite.get('tests'))==expected_cases
            assert int(test_suite.get('failures'))==expected_failures
            assert int(test_suite.get('errors'))==expected_errors
            assert int(test_suite.get('skipped'))==0
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before
            summary['junit_checks'].append({'file':str(xml.relative_to(root)),'passed':True})
            entries.append(row)
        summary['suites'][name]={'suite_hash':suite.hash,'models':entries}
    (root/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Recorded model validation','',
           'Local Ollama configurations; small synthetic suites, not a general model ranking.',
           'Repeats change deterministic tool order. Different suite scores are not interchangeable.','',
           '| Suite | Model | Passed/scored | Errors | Truncations | Repeat disagreements |',
           '| --- | --- | --- | --- | --- | --- |']
    for name,suite in summary['suites'].items():
        for row in suite['models']:
            if 'scored' not in row:
                lines.append(f"| {name} | {row['model']} | no results | — | — | — |")
                continue
            changes=str(len(row['repeat_disagreements'])) if row['repeat_pairs'] else 'n/a'
            lines.append(f"| {name} | {row['model']} | {row['passed']}/{row['scored']} | {row['errors']} | {row['truncated']} | {changes} |")
    lines += ['',f"Validated {len(summary['junit_checks'])} JUnit exports against raw outcomes.",
              'See analysis.json for per-padding scores, failure patterns and repeat-disagreement IDs.']
    (root/'analysis.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':
    main()
