// Purpose: bounded C ABI for Metal compute used by the portable Python worker.
// Inputs: owned float32 RGB tiles and validated packed parameters. Outputs: copied
// RGB/gamut and optional six-channel readouts only after successful GPU completion.
// No RAW/files/UI access. The v2 entry point retains ordinary RGB compatibility.
// Shared buffers are reused within one disposable worker; CPU fallback is caller-owned.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <algorithm>
#include <cstring>
#include <mutex>

struct Context {
    id<MTLDevice> device;
    id<MTLCommandQueue> queue;
    id<MTLComputePipelineState> pipeline;
    id<MTLBuffer> input, output, gamut, readouts;
    size_t capacity=0, limit=0;
    bool capturesReadouts=false;
    double seconds=0;
    std::mutex lock;
};
static void errorText(char *dst,size_t size,NSString *message) {
    if(dst && size) snprintf(dst,size,"%s",message.UTF8String ?: "Metal error");
}
extern "C" void *lr_metal_create(const char *source,size_t limit,char *error,size_t size) {
    @autoreleasepool {
        Context *c=new Context();
        c->device=MTLCreateSystemDefaultDevice();c->limit=limit;
        if(!c->device || !c->device.hasUnifiedMemory){errorText(error,size,@"Metal unified-memory GPU unavailable");delete c;return nullptr;}
        MTLCompileOptions *options=[MTLCompileOptions new];options.fastMathEnabled=NO;
        NSError *e=nil;
        id<MTLLibrary> library=[c->device newLibraryWithSource:[NSString stringWithUTF8String:source] options:options error:&e];
        if(!library){errorText(error,size,e.localizedDescription);delete c;return nullptr;}
        c->pipeline=[c->device newComputePipelineStateWithFunction:[library newFunctionWithName:@"grade_output"] error:&e];
        c->queue=[c->device newCommandQueue];
        if(!c->pipeline || !c->queue){errorText(error,size,e.localizedDescription ?: @"Metal queue unavailable");delete c;return nullptr;}
        return c;
    }
}
extern "C" void lr_metal_destroy(void *context){delete static_cast<Context *>(context);}
extern "C" const char *lr_metal_device(void *context){return static_cast<Context *>(context)->device.name.UTF8String;}
extern "C" size_t lr_metal_allocated(void *context){
    Context *c=static_cast<Context *>(context);
    return c->capacity*(c->capturesReadouts ? 49 : 25);
}
extern "C" double lr_metal_seconds(void *context){return static_cast<Context *>(context)->seconds;}
extern "C" unsigned int lr_metal_parameter_count(){return 640;}
extern "C" int lr_metal_run_v3(void *context,const float *input,float *output,unsigned char *gamut,float *readouts,
                             unsigned int count,const float *params,unsigned int parameterCount,char *error,size_t size) {
    if(parameterCount!=640){errorText(error,size,@"Metal parameter layout mismatch");return 1;}
    if(!context || !input || !output || !gamut || !params || count==0)return 1;
    const bool capture=readouts!=nullptr;
    if((params[55]!=0)!=capture || (capture && params[54]!=0)){
        errorText(error,size,@"Metal readout buffer does not match parameters");return 1;
    }
    Context *c=static_cast<Context *>(context);std::lock_guard<std::mutex> guard(c->lock);
    @autoreleasepool {
        const size_t bytesPerPixel=capture ? 49 : 25;
        if(count>4000000 || size_t(count)*bytesPerPixel>c->limit){errorText(error,size,@"Tile exceeds Metal shared-buffer limit");return 2;}
        if(count>c->capacity || capture!=c->capturesReadouts){
            // Release previous buffers before allocating the new bounded capacity.
            c->input=nil;c->output=nil;c->gamut=nil;c->readouts=nil;c->capacity=0;
            c->capturesReadouts=capture;
            c->input=[c->device newBufferWithLength:size_t(count)*12 options:MTLResourceStorageModeShared];
            c->output=[c->device newBufferWithLength:size_t(count)*12 options:MTLResourceStorageModeShared];
            c->gamut=[c->device newBufferWithLength:count options:MTLResourceStorageModeShared];
            if(capture)c->readouts=[c->device newBufferWithLength:size_t(count)*24 options:MTLResourceStorageModeShared];
            if(!c->input || !c->output || !c->gamut || (capture && !c->readouts)){
                c->input=nil;c->output=nil;c->gamut=nil;c->readouts=nil;
                errorText(error,size,@"Metal allocation failed");return 3;
            }
            c->capacity=count;
        }
        memcpy(c->input.contents,input,size_t(count)*12);
        id<MTLCommandBuffer> command=[c->queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];
        if(!command || !encoder){errorText(error,size,@"Metal command allocation failed");return 4;}
        [encoder setComputePipelineState:c->pipeline];
        [encoder setBuffer:c->input offset:0 atIndex:0];[encoder setBuffer:c->output offset:0 atIndex:1];
        [encoder setBuffer:c->gamut offset:0 atIndex:2];[encoder setBytes:params length:640*sizeof(float) atIndex:3];
        [encoder setBytes:&count length:sizeof(count) atIndex:4];
        // A non-null binding is required even when the uniform flag skips it.
        [encoder setBuffer:(capture ? c->readouts : c->output) offset:0 atIndex:5];
        NSUInteger width=std::min(NSUInteger(256),c->pipeline.maxTotalThreadsPerThreadgroup);
        [encoder dispatchThreads:MTLSizeMake(count,1,1) threadsPerThreadgroup:MTLSizeMake(width,1,1)];
        [encoder endEncoding];[command commit];[command waitUntilCompleted];
        if(command.status!=MTLCommandBufferStatusCompleted){errorText(error,size,command.error.localizedDescription ?: @"Metal command failed");return 5;}
        c->seconds=std::max(0.0,command.GPUEndTime-command.GPUStartTime);
        memcpy(output,c->output.contents,size_t(count)*12);memcpy(gamut,c->gamut.contents,count);
        if(capture)memcpy(readouts,c->readouts.contents,size_t(count)*24);
        return 0;
    }
}
extern "C" int lr_metal_run_v2(void *context,const float *input,float *output,unsigned char *gamut,
                             unsigned int count,const float *params,unsigned int parameterCount,char *error,size_t size) {
    return lr_metal_run_v3(context,input,output,gamut,nullptr,count,params,parameterCount,error,size);
}
