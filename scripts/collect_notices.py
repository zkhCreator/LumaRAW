"""Collect dependency license metadata for the locally bundled engine, never secrets."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
for name in ['jsonschema','jsonschema-specifications','referencing','rpds-py','attrs','typing-extensions','packaging']:
    dist=distribution(name);folder=root/'licenses'/name;folder.mkdir(exist_ok=True)
    found=[]
    for file in dist.files or []:
        if any(part.lower() in ('licenses','license','license.txt','license.md','copying','copying.txt') for part in file.parts):
            source=dist.locate_file(file)
            if source.is_file() and source.suffix != ".py":
                dest=folder/source.name
                if dest.exists() and dest.read_bytes()!=source.read_bytes():dest=folder/(str(file).replace('/','_'))
                shutil.copy2(source,dest);found.append(dest.name)
    print(name,dist.version,found)
