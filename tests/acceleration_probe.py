"""Compare packaged CPU/Metal workers using the same read-only NEF and recipe.

Records cold/warm wall times, stages, RSS, output parity and source digest. GPU
initialization/copies are included. Cold means empty app cache, not OS disk cache.
Sequential workers prevent the benchmark from creating its own memory contention.
"""
import argparse,hashlib,json,os,shutil,statistics,subprocess,threading,time
from pathlib import Path
import psutil
import numpy as np
from PIL import Image
import tifffile

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',required=True,type=Path);parser.add_argument('--fixture',required=True,type=Path);parser.add_argument('--work',required=True,type=Path);parser.add_argument('--preset',choices=['creative','neutral','mixer','bw_mixer','point_curves','parametric'],default='creative')
    parser.add_argument('--curve-tones',action='store_true',help='Include targeted input maps; omit the baseline image as during interactive drafts')
    parser.add_argument('--mixer-target',choices=['hsl','bw'],help='Include sparse color target maps; omit before images')
    a=parser.parse_args()
    if a.work.exists():raise SystemExit('Choose new work directory')
    a.work.mkdir(parents=True);a.work=a.work.resolve();a.engine=a.engine.resolve();a.fixture=a.fixture.resolve()
    before=digest(a.fixture);runs=[]
    recipe={'exposure':.35,'highlights':-25,'shadows':20,'contrast':12,'vibrance':18,'curve_midtones':4,'blue_hue':-9,'blue_sat':12}
    if a.preset=='neutral':recipe={}
    if a.preset in ('mixer','bw_mixer'):
        recipe.update(yellow_hue=12,aqua_hue=-9,purple_hue=15,magenta_hue=-12,yellow_sat=-20,aqua_sat=25,purple_sat=30,magenta_sat=-15,
                      red_lum=-15,orange_lum=20,yellow_lum=-25,green_lum=15,aqua_lum=-30,blue_lum=35,purple_lum=-20,magenta_lum=25)
    if a.preset=='bw_mixer':
        recipe.update(monochrome=True,red_bw=30,orange_bw=15,yellow_bw=20,green_bw=-15,aqua_bw=-25,blue_bw=-35,purple_bw=25,magenta_bw=10)
    if a.preset in ('point_curves','parametric'):
        recipe.update(curve_rgb_points=[[0,.03],[.25,.18],[.75,.83],[1,.98]],
                      curve_red_points=[[0,0],[.4,.46],[1,1]],
                      curve_green_points=[[0,.02],[.6,.56],[1,1]],
                      curve_blue_points=[[.04,0],[.45,.5],[.96,1]])
    if a.preset=='parametric':
        recipe.update(parametric_shadows=65,parametric_darks=-45,parametric_lights=35,parametric_highlights=-60,parametric_splits=[.18,.52,.83])
    def run(mode,operation,label,cache):
        dest=a.work/f'{label}-{mode}';dest.mkdir()
        budget=min(4096,int(psutil.virtual_memory().available/1024**2*.7))
        request={'operation':operation,'path':str(a.fixture),'recipe':recipe,'cache':str(cache),'budget_mb':budget,'compute_backend':mode,'destination':str(dest),'format':'tiff16','job_id':len(runs)+1,'options':{'space':'prophoto','max_edge':0}}
        if operation=='detail':request['detail']={'width':1280,'height':900}
        if a.curve_tones and operation!='export':
            request.update(include_curve_tones=True,include_before=False)
        if a.mixer_target and operation!='export':
            request.update(mixer_target=a.mixer_target,include_before=False)
        start=time.perf_counter()
        p=subprocess.Popen([str(a.engine),'--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'2'})
        peak=[0.];done=threading.Event()
        def sample():
            while not done.wait(.02):
                try:peak[0]=max(peak[0],psutil.Process(p.pid).memory_info().rss/1024**2)
                except psutil.NoSuchProcess:break
        thread=threading.Thread(target=sample);thread.start()
        stdout,stderr=p.communicate(json.dumps(request).encode()+b'\n',timeout=300);done.set();thread.join()
        elapsed=time.perf_counter()-start
        result=json.loads(stdout);assert p.returncode==0 and result['ok'],result
        if operation!='export':
            saved=dest/'preview.png';shutil.copy2(result['preview'],saved);result['preview']=str(saved)
        if mode=='metal':assert result['processing']['metal_grade_tiles']>0,result
        item={'label':label,'mode':mode,'operation':operation,'wall_seconds':round(elapsed,6),'rss_peak_mb':round(peak[0],2),'processing':result['processing'],'output':result.get('output',result.get('preview'))};runs.append(item)
        if a.curve_tones and operation!='export':
            receipt=result['curve_tones'];tone_path=Path(receipt['path'])
            assert receipt['stage']=='pre-parametric-v1'
            assert (receipt['width'],receipt['height'])==(result['width'],result['height'])
            assert tone_path.stat().st_size==16+receipt['width']*receipt['height']*4
            assert receipt['cache_hit']==label.startswith('warm-preview')
            values=np.frombuffer(tone_path.read_bytes()[16:],'<f4')
            assert np.isfinite(values).all() and values.min()>=0 and values.max()<=1
            item['curve_tones']={**receipt,'sha256':digest(tone_path),'bytes':tone_path.stat().st_size}
            if receipt['cache_hit']:assert 'curve_input_tones' not in result['processing']['stages']
        if a.mixer_target and operation!='export':
            receipt=result['mixer_target'];map_path=Path(receipt['path'])
            assert receipt['stage']=='mixer-target-v1' and receipt['mode']==a.mixer_target
            assert (receipt['width'],receipt['height'])==(result['width'],result['height'])
            assert map_path.stat().st_size==16+receipt['width']*receipt['height']*16
            assert receipt['cache_hit']==label.startswith('warm-preview')
            packed=np.frombuffer(map_path.read_bytes()[16:],'<u4').reshape(-1,4)
            counts=packed[:,0]>>24;assert counts.max()<=3
            for slot in range(3):
                used=counts>slot;weights=packed[used,slot+1].copy().view('<f4')
                assert np.all(((packed[used,0]>>(8*slot))&255)<8)
                assert np.isfinite(weights).all() and np.all((weights>0)&(weights<=1))
            item['mixer_target']={**receipt,'sha256':digest(map_path),'bytes':map_path.stat().st_size,'max_bands':int(counts.max())}
            if receipt['cache_hit']:assert 'mixer_target_weights' not in result['processing']['stages']
        return item
    pairs=[]
    # Alternate order between passes. The source cache is private per backend.
    for i in range(3):
        values={mode:run(mode,'preview','cold-preview' if i==0 else f'warm-preview-{i}',a.work/f'cache-{mode}') for mode in (['cpu','metal'] if i%2==0 else ['metal','cpu'])}
        pairs.append(values)
    for op in ['export','detail']:
        pairs.append({mode:run(mode,op,op,a.work/f'cache-{mode}') for mode in ['metal','cpu']})
    differences=[]
    for pair in pairs:
        def pixels(item):return tifffile.imread(item['output']) if item['operation']=='export' else np.array(Image.open(item['output']))
        cpu=pixels(pair['cpu']);gpu=pixels(pair['metal']);assert cpu.shape==gpu.shape
        diff=np.abs(cpu.astype(np.int32)-gpu.astype(np.int32));limit=8 if cpu.dtype==np.uint16 else 1
        differences.append({'label':pair['cpu']['label'],'shape':list(cpu.shape),'dtype':str(cpu.dtype),'max_code_difference':int(diff.max()),'mean_code_difference':float(diff.mean()),'limit':limit})
        assert diff.max()<=limit,differences[-1]
        if a.curve_tones and pair['cpu']['operation']!='export':
            assert pair['cpu']['curve_tones']['sha256']==pair['metal']['curve_tones']['sha256']
        if a.mixer_target and pair['cpu']['operation']!='export':
            assert pair['cpu']['mixer_target']['sha256']==pair['metal']['mixer_target']['sha256']
    assert digest(a.fixture)==before
    summary=[]
    for pair in pairs:
        cpu=pair['cpu'];gpu=pair['metal'];cs=cpu['processing']['stages']['grade_and_output']['seconds'];gs=gpu['processing']['stages']['grade_and_output']['seconds']
        summary.append({'label':cpu['label'],'cpu_wall_seconds':cpu['wall_seconds'],'metal_wall_seconds':gpu['wall_seconds'],'end_to_end_speedup':round(cpu['wall_seconds']/gpu['wall_seconds'],3),'grade_output_speedup_including_init_and_copies':round(cs/gs,3)})
    result={'engine_sha256':digest(a.engine),'source_sha256':before,'original_unchanged':True,'recipe':recipe,'comparisons':summary,'pixel_parity':differences,'runs':runs,'scope':'One real Nikon NEF on this host; not a general benchmark. Empty app cache does not mean cold OS/Metal cache.'}
    (a.work/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
