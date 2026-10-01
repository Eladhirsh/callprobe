"""Check valid, missing, wrong-valued and extra-field arguments in both contracts."""
from copy import deepcopy
from pathlib import Path
from callprobe.loader import load_suite
from callprobe.scoring import _judge
root=Path(__file__).resolve().parent
nested=load_suite(str(root/'nested'));flat=load_suite(str(root/'flat'))
checks=0
for nt,ft in zip(nested.tasks,flat.tasks):
    assert nt.id==ft.id and nt.messages==ft.messages
    if nt.expect.type!='call':
        assert nt.expect==ft.expect
        continue
    ntool=nested.bundles[nt.bundle].by_name(nt.expect.tool)
    ftool=flat.bundles[ft.bundle].by_name(ft.expect.tool)
    groups=ntool.parameters['properties']
    def flatten(args):
        return {k:v for obj in args.values() for k,v in obj.items()}
    candidates=[deepcopy(nt.expect.args)]
    for group,obj in nt.expect.args.items():
        for key in obj:
            missing=deepcopy(nt.expect.args);del missing[group][key];candidates.append(missing)
            wrong=deepcopy(nt.expect.args);wrong[group][key]=['wrong type'];candidates.append(wrong)
        for extra in set(groups[group]['properties'])-set(obj):
            added=deepcopy(nt.expect.args)
            added[group][extra]='inbox' if extra=='folder' else 1
            candidates.append(added)
    for args in candidates:
        n=_judge(args,ntool,nt);f=_judge(flatten(args),ftool,ft)
        assert n[:2]==f[:2], (nt.id,args,n,f)
        checks+=1
print(f'{checks} paired argument checks agree; prompts and abstention expectations match')
