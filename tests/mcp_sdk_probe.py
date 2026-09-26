"""Verify LumaRAW with the official MCP Python client, not a hand-written parser."""
import asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    engine=Path(os.environ['LUMARAW_ENGINE'])
    root=Path(os.environ['LUMARAW_PROBE_ROOT'])
    root.mkdir(parents=True,exist_ok=True)
    server=StdioServerParameters(command=str(engine),args=['--mcp','--catalog',str(root/'catalog')])
    async with stdio_client(server) as streams:
        async with ClientSession(*streams) as session:
            init=await session.initialize()
            listed=await session.list_tools()
            imported=await session.call_tool('lumaraw_import_photos',{'paths':[os.environ['LUMARAW_PROBE_NEF']]})
            assert not imported.is_error
            setting=await session.call_tool('lumaraw_settings',{'compute_backend':'metal'})
            assert not setting.is_error
            photo=await session.call_tool('lumaraw_get_photo',{'photo_id':1})
            value=json.loads(photo.content[0].text)
            edited=await session.call_tool('lumaraw_edit_photo',{'photo_id':1,'expected_revision':value['revision'],'patch':{'exposure':0.3,'shadows':12}})
            assert not edited.is_error
            preview=await session.call_tool('lumaraw_preview_photo',{'photo_id':1,'detail':{'width':640,'height':480}})
            assert not preview.is_error,preview
            receipt=json.loads(preview.content[0].text);assert Path(receipt['preview']).exists()
            assert receipt['processing']['metal_grade_tiles']>0,receipt['processing']
            submitted=await session.call_tool('lumaraw_enqueue_exports',{'photo_ids':[1],'destination':str(root/'export'),'format':'tiff16','options':{'space':'prophoto','max_edge':1024},'request_key':'official-client-smoke'})
            assert not submitted.is_error
            job_id=json.loads(submitted.content[0].text)['job_ids'][0]
            for _ in range(100):
                jobs=await session.call_tool('lumaraw_list_jobs',{})
                value=json.loads(jobs.content[0].text)
                job=next(j for j in value['jobs'] if j['id']==job_id)
                if job['state'] not in ('pending','running'):break
                await asyncio.sleep(.1)
            assert job['state']=='done',job
            assert Path(job['output']).exists()
            assert job['processing']['metal_grade_tiles']>0,job
            report={'processing':job['processing'],'preview_processing':receipt['processing'],'sdk':'official mcp Python ClientSession','protocol':init.protocol_version,'tools':len(listed.tools),'preview':receipt['preview'],'output':job['output'],'state':job['state'],'ok':True}
            (root/'mcp-sdk-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
asyncio.run(main())
