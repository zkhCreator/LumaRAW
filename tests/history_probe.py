"""Measure warm indexed timeline navigation without image work or desktop input.

Inputs: a new private output directory and synthetic step count. Outputs: service
latencies, page bytes, RSS and original/recipe invariants. Setup is excluded from
timings; writes include connection/schema checks and SQLite commits. These are
catalog timings, not preview or complete user-interaction latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource

from PIL import Image

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=100000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 100<=args.steps<=1000000 or not 1<=args.samples<=1000:raise ValueError('Counts outside probe bounds')
    root=args.work.resolve();root.mkdir()
    path=root/'original.png';Image.new('RGB',(64,48),'navy').save(path)
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'});s.dispatch('import_photos',{'paths':[str(path)]})
        base=json.dumps(Recipe().dict());recipes=[json.dumps(Recipe(exposure=i).dict()) for i in (1,2)]
        with s.catalog() as c,c.db:
            c.db.executemany('INSERT INTO history(id,photo_id,recipe,label,created) VALUES(?,1,?,?,?)',
                            ((i,recipes[i%2],f'Step {i}',float(i)) for i in range(1,args.steps+1)))
            c.db.execute('UPDATE photos SET recipe=?,history_base_recipe=?,history_cursor=? WHERE id=1',
                         (recipes[args.steps%2],base,args.steps))
            c.db.execute('UPDATE history_identity SET next_id=?',(args.steps+1,))
        revision=0
        def page(before=None):
            params={'photo_id':1,'expected_revision':revision}
            if before is not None:params['before_id']=before
            return s.dispatch('list_history',params)
        def mutate(method,**params):
            nonlocal revision
            result=s.dispatch(method,{'photo_id':1,'expected_revision':revision,**params})
            revision=result['revision'];return result
        report={'system':platform.platform(),'machine':platform.machine(),'steps':args.steps,
                'scope':'warm in-process service; SQLite connection/validation/commits included; setup, IPC, image workers and UI excluded'}
        report['newest_page']=measure(page,args.samples)
        report['deep_page']=measure(lambda:page(args.steps//2),args.samples)
        report['page_bytes']=len(json.dumps(page()).encode())
        report['undo_redo_pair']=measure(lambda:(mutate('undo_photo'),mutate('redo_photo')),args.samples)
        report['jump_baseline_head_pair']=measure(lambda:(mutate('select_history',step_id=0),mutate('select_history',step_id=args.steps)),args.samples)
        report['append']=measure(lambda:mutate('edit_photo',patch={'exposure':(revision%2+1)/3}),args.samples)
        assert len(page()['steps'])==60 and s.peak==0
        mutate('select_history',step_id=args.steps//2)
        report['replace_future_half_once']=measure(lambda:mutate('edit_photo',patch={'exposure':-3}),1)
        report['clear_remaining_once']=measure(lambda:mutate('clear_history'),1)
        assert len(page()['steps'])==1 and not page()['can_redo']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==original
        report['worker_peak_mb']=s.peak
        report['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024)
        report['original_unchanged']=True
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
