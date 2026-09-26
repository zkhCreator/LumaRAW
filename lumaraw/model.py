"""Edit recipe contract shared by catalog, UI, and worker.

Purpose: validate non-destructive, versioned edits before any processing.
Inputs: user controls or stored JSON. Outputs: a small serializable recipe.
Non-goals: no image I/O, no absolute Kelvin calibration, no Nikon Picture Control.
Temperature and tint are relative adjustments to the camera's as-shot balance.
"""
from dataclasses import asdict, dataclass, fields, field
import math

RAW_EXTENSIONS = {'.nef', '.nrw', '.dng', '.arw', '.cr2', '.cr3', '.raf', '.rw2', '.orf'}
IMAGE_EXTENSIONS = RAW_EXTENSIONS | {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
LIMITS = {
    'exposure': (-5, 5), 'temperature': (-100, 100), 'tint': (-100, 100),
    'contrast': (-100, 100), 'highlights': (-100, 100), 'shadows': (-100, 100),
    'whites': (-100, 100), 'blacks': (-100, 100), 'saturation': (-100, 100),
    'vibrance': (-100, 100), 'curve_shadows': (-30, 30), 'curve_midtones': (-30, 30),
    'curve_lights': (-30, 30), 'red_hue': (-30, 30), 'red_sat': (-100, 100),
    'orange_hue': (-30, 30), 'orange_sat': (-100, 100), 'green_hue': (-30, 30),
    'green_sat': (-100, 100), 'blue_hue': (-30, 30), 'blue_sat': (-100, 100),
    'luma_noise': (0, 100), 'chroma_noise': (0, 100), 'sharpen': (0, 150),
    'sharpen_radius': (.3, 3), 'detail_protect': (0, 100),
    'distortion': (-100, 100), 'vignette': (-100, 100),
    'ca_red': (-50, 50), 'ca_blue': (-50, 50), 'defringe': (0, 100),
    'straighten': (-20, 20), 'perspective_v': (-50, 50), 'perspective_h': (-50, 50),
    'geometry_scale': (1, 2), 'lut_amount': (0, 100),
}

@dataclass(frozen=True)
class Recipe:
    version: int = 2
    exposure: float = 0
    temperature: float = 0
    tint: float = 0
    contrast: float = 0
    highlights: float = 0
    shadows: float = 0
    whites: float = 0
    blacks: float = 0
    saturation: float = 0
    vibrance: float = 0
    curve_shadows: float = 0
    curve_midtones: float = 0
    curve_lights: float = 0
    red_hue: float = 0
    red_sat: float = 0
    orange_hue: float = 0
    orange_sat: float = 0
    green_hue: float = 0
    green_sat: float = 0
    blue_hue: float = 0
    blue_sat: float = 0
    monochrome: bool = False
    highlight_recovery: bool = False
    rotation: int = 0
    crop: str = 'original'
    crop_box: list = field(default_factory=lambda: [0., 0., 1., 1.])
    straighten: float = 0
    perspective_v: float = 0
    perspective_h: float = 0
    geometry_scale: float = 1
    distortion: float = 0
    vignette: float = 0
    ca_red: float = 0
    ca_blue: float = 0
    defringe: float = 0
    luma_noise: float = 0
    chroma_noise: float = 0
    sharpen: float = 0
    sharpen_radius: float = 1
    detail_protect: float = 40
    curve_points: list = field(default_factory=lambda: [[0., 0.], [1., 1.]])
    masks: list = field(default_factory=list)
    camera_profile: dict = field(default_factory=dict)
    lut: dict = field(default_factory=dict)
    lut_amount: float = 100

    def __post_init__(self):
        if self.version != 2:
            raise ValueError('Unsupported recipe version')
        for name, (lo, hi) in LIMITS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f'Parameter out of range: {name}')
        if type(self.rotation) is not int or self.rotation not in (0, 90, 180, 270):
            raise ValueError('Rotation must be 0 / 90 / 180 / 270')
        if self.crop not in ('original', '1:1', '3:2', '4:5', '16:9'):
            raise ValueError('Unsupported crop ratio')
        validate_extras(self)
        if type(self.monochrome) is not bool or type(self.highlight_recovery) is not bool:
            raise ValueError('Invalid boolean parameter')

    def dict(self):
        return asdict(self)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError('Invalid recipe parameters')
        value = dict(value)
        if value.get('version') == 1:
            value['version'] = 2
        return cls(**value)


def number(value, lo, hi):
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


def validate_extras(r):
    box = r.crop_box
    if not isinstance(box, list) or len(box) != 4 or not all(number(x, 0, 1) for x in box) or box[2] - box[0] < .01 or box[3] - box[1] < .01:
        raise ValueError('Crop bounds must be inside the photo with width and height of at least 1%')
    points = r.curve_points
    if not isinstance(points, list) or not 2 <= len(points) <= 16 or any(not isinstance(p, list) or len(p) != 2 or not all(number(v, 0, 1) for v in p) for p in points):
        raise ValueError('A curve requires 2–16 valid control points')
    if points[0][0] != 0 or points[-1][0] != 1 or any(b[0] <= a[0] or b[1] < a[1] for a, b in zip(points, points[1:])):
        raise ValueError('Curve X must increase, Y must not decrease, and the curve must cover 0–1')
    if not isinstance(r.masks, list) or len(r.masks) > 12:
        raise ValueError('At most 12 local masks are allowed')
    for m in r.masks:
        allowed = {'kind','name','enabled','invert','x','y','x2','y2','radius','feather','low','high','exposure','saturation','points'}
        if not isinstance(m, dict) or set(m) - allowed or m.get('kind') not in ('radial','linear','luminance','brush'):
            raise ValueError('Invalid mask')
        for key, lo, hi, default in [('x',0,1,.5),('y',0,1,.5),('x2',0,1,1),('y2',0,1,1),('radius',.01,1,.25),('feather',.01,1,.5),('low',0,1,0),('high',0,1,1),('exposure',-4,4,0),('saturation',-100,100,0)]:
            if not number(m.get(key, default), lo, hi):
                raise ValueError('Mask parameter out of range: ' + key)
        if m.get('low',0) > m.get('high',1) or any(type(m.get(k, True)) is not bool for k in ('enabled','invert') if k in m):
            raise ValueError('Invalid mask bounds or toggle')
        if not isinstance(m.get('name',''),str) or len(m.get('name','')) > 80:
            raise ValueError('Invalid mask name')
        points = m.get('points', [])
        if not isinstance(points, list) or len(points) > 500 or any(not isinstance(p,list) or len(p)!=2 or not all(number(v,0,1) for v in p) for p in points):
            raise ValueError('Each brush mask supports at most 500 points')
    if not isinstance(r.camera_profile, dict):
        raise ValueError('Invalid camera profile')
    if r.camera_profile:
        p = r.camera_profile
        if any(not isinstance(p.get(k,''),str) or len(p.get(k,''))>256 for k in ('name','lighting')):
            raise ValueError('Profile name and lighting description must be short text')
        if p.get('space') != 'LibRaw-ProPhoto-D65-linear' or not isinstance(p.get('camera'),str) or not p['camera'].strip():
            raise ValueError('A profile must identify a camera and declare its linear color space')
        matrix = p.get('matrix')
        if not isinstance(matrix,list) or len(matrix)!=3 or any(not isinstance(row,list) or len(row)!=3 or not all(number(v,-4,4) for v in row) for row in matrix):
            raise ValueError('A profile requires a valid 3×3 matrix')
        if len(str(p)) > 16384:
            raise ValueError('Camera profile is too large')
    if not isinstance(r.lut,dict) or (r.lut and (set(r.lut)-{'path','sha256','title'} or not isinstance(r.lut.get('path'),str) or not isinstance(r.lut.get('sha256'),str) or len(r.lut['sha256']) != 64)):
        raise ValueError('Invalid LUT reference')
    if r.lut and (not isinstance(r.lut.get('title',''),str) or len(r.lut.get('title',''))>256 or any(c not in '0123456789abcdef' for c in r.lut['sha256'])):
        raise ValueError('Invalid LUT name or checksum')


@dataclass(frozen=True)
class ExportOptions:
    space: str = 'srgb'
    max_edge: int = 0
    quality: int = 96
    output_sharpen: float = 0
    name: str = '{stem}-Luma-{seq}'
    priority: int = 0
    def __post_init__(self):
        if self.space not in ('srgb','adobe','p3','prophoto'):
            raise ValueError('Unsupported output color space')
        if type(self.max_edge) is not int or not 0 <= self.max_edge <= 16000 or type(self.quality) is not int or not 1 <= self.quality <= 100:
            raise ValueError('Export size or quality is out of range')
        if not number(self.output_sharpen,0,150) or type(self.priority) is not int or not 0 <= self.priority <= 9:
            raise ValueError('Invalid export options')
        import string
        if not isinstance(self.name,str) or not self.name or len(self.name)>120 or any(c in self.name for c in '/\\:'):
            raise ValueError('Filename templates cannot contain paths or colons')
        for _, key, spec, conversion in string.Formatter().parse(self.name):
            if key is not None and (key not in ('stem','seq','width','height','space') or spec or conversion):
                raise ValueError('Filenames support only {stem} {seq} {width} {height} {space}')
    def dict(self):
        return asdict(self)
    @classmethod
    def parse(cls, value=None):
        return cls(**(value or {}))


SYNC_GROUPS = {
    'White Balance': ['temperature','tint'],
    'Light': ['exposure','contrast','highlights','shadows','whites','blacks','highlight_recovery'],
    'Color': ['saturation','vibrance','monochrome','red_hue','red_sat','orange_hue','orange_sat','green_hue','green_sat','blue_hue','blue_sat'],
    'Tone Curve': ['curve_shadows','curve_midtones','curve_lights','curve_points'],
    'Detail': ['luma_noise','chroma_noise','sharpen','sharpen_radius','detail_protect','defringe'],
    'Lens': ['distortion','vignette','ca_red','ca_blue'],
    'Composition': ['rotation','crop','crop_box','straighten','perspective_h','perspective_v','geometry_scale'],
    'Local Masks': ['masks'], 'Camera Profile': ['camera_profile'], 'LUT': ['lut','lut_amount'],
}

PRESETS = {
    'Camera Baseline': Recipe(),
    'Soft Portrait': Recipe(exposure=.2, contrast=-12, highlights=-25, shadows=12, vibrance=8, orange_sat=-8),
    'Mountain Teal': Recipe(contrast=12, highlights=-30, shadows=16, vibrance=18, green_hue=12, green_sat=-12, blue_sat=12),
    'Warm Film': Recipe(temperature=12, contrast=-8, blacks=18, highlights=-22, saturation=-12, curve_shadows=3),
    'Silver Monochrome': Recipe(monochrome=True, contrast=22, highlights=-20, shadows=10),
}


def estimate_export_bytes(width,height,options,fmt):
    if options.max_edge and max(width,height)>options.max_edge:
        scale=options.max_edge/max(width,height);width=max(1,round(width*scale));height=max(1,round(height*scale))
    # JPEG quality depends on content; use conservative 6 bytes/pixel plus scratch.
    return int(width*height*(6 if fmt=='tiff16' else 9)+4*1024**2)
