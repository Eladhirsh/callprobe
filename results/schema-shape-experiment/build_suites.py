"""Create equivalent mail contracts using the installed release's example."""
from copy import deepcopy
from pathlib import Path
import yaml
from callprobe.examples import generate_example_suite
from callprobe.loader import load_suite
from callprobe.validate import validate_suite

root = Path(__file__).resolve().parent
files, _ = generate_example_suite('mail-sandbox', 'nested')
for name in ('nested', 'flat'):
    out = root / name
    out.mkdir(exist_ok=True)
    for filename in ('tools.yaml', 'tasks.yaml', 'distractors.yaml', 'suite.yaml'):
        (out / filename).write_text(files[filename])
tools = yaml.safe_load(files['tools.yaml'])
tasks = yaml.safe_load(files['tasks.yaml'])
original_tools = deepcopy(tools)
for tool in tools['bundles']['main']:
    schema = tool['parameters']
    props, required = {}, []
    assert set(schema['required']) == set(schema['properties'])
    for group in schema['properties'].values():
        assert group['type'] == 'object' and group['additionalProperties'] is False
        assert not set(props).intersection(group['properties']), 'ambiguous flattened names'
        props.update(deepcopy(group['properties']))
        required.extend(group.get('required', []))
    tool['parameters'] = {'type': 'object', 'properties': props,
                          'required': required, 'additionalProperties': False}
by_name = {t['name']: t for t in tools['bundles']['main']}
for task in tasks['tasks']:
    expect = task['expect']
    if expect['type'] != 'call':
        continue
    assert not expect.get('arg_checks')
    expected = {}
    for values in expect['args'].values():
        assert isinstance(values, dict)
        expected.update(values)
    expect['args'] = expected
    # Nested args compare entire objects. Preserve that exactness: optional
    # keys absent from the nested expectation must also be absent when flat.
    absent = set(by_name[expect['tool']]['parameters']['properties']) - set(expected)
    if absent:
        expect['arg_checks'] = [{'path': k, 'op': 'absent'} for k in sorted(absent)]
(root/'flat/tools.yaml').write_text(yaml.safe_dump(tools, sort_keys=False))
(root/'flat/tasks.yaml').write_text(yaml.safe_dump(tasks, sort_keys=False, allow_unicode=True))
for before, after in zip(original_tools['bundles']['main'], tools['bundles']['main']):
    assert before['name'] == after['name'] and before['description'] == after['description']
original_tasks = yaml.safe_load(files['tasks.yaml'])['tasks']
assert all(a['messages'] == b['messages'] for a,b in zip(original_tasks, tasks['tasks']))
for variant in ('nested', 'flat'):
    suite = load_suite(str(root/variant))
    problems = validate_suite(suite)
    assert not problems, problems
    print(variant, suite.hash, len(suite.tasks), 'tasks validated')
