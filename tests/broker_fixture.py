"""Start an isolated differently tagged broker for native connection regression.

Inputs: a new test catalog and generated photo paths. Output: an idle paused queue
with one immutable job. The test app switches this broker through normal handoff.
This fixture never selects a personal catalog or terminates an unrelated process.
"""
import argparse
from pathlib import Path

from lumaraw import bridge, broker_lifecycle
from lumaraw.runtime import engine_identity
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--photo',action='append',required=True)
    args=parser.parse_args()
    if args.catalog.exists() and any(args.catalog.iterdir()):
        raise SystemExit('The fixture requires a new empty catalog')
    identity={**engine_identity(),'digest':'0'*64}
    bridge.engine_identity=lambda:identity
    broker_lifecycle.engine_identity=lambda:identity
    initialize=Service.__init__
    def configured(self,*values,**named):
        initialize(self,*values,**named)
        self.dispatch('queue_control',{'action':'pause'})
        self.dispatch('import_photos',{'paths':args.photo})
        self.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':0.75}})
        self.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(args.catalog/'test-exports'),
            'format':'jpeg','request_key':'native-connection-fixture'})
    Service.__init__=configured
    bridge.serve(args.catalog)


if __name__=='__main__':main()
