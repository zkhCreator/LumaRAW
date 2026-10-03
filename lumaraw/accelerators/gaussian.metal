// Purpose: bounded scalar Gaussian passes for optional Presence acceleration.
// Inputs: FP32 plane, normalized weights and checked dimensions/radius/axis.
// Output: one plane; the C ABI owns completion, capacity and copying. No grading,
// geometry, scene inference or RAW work. CPU defines nearest-edge/truncate semantics.
// Center differences keep constant fields exact. Compensated summation bounds
// error at broad kernels/high-contrast edges, including one-row/column planes.
#include <metal_stdlib>
using namespace metal;

kernel void presence_gaussian(device const float *input [[buffer(0)]],
                              device float *output [[buffer(1)]],
                              constant float *weights [[buffer(2)]],
                              constant uint4 &p [[buffer(3)]],
                              uint i [[thread_position_in_grid]]) {
    uint width=p.x,height=p.y,radius=p.z,axis=p.w;
    if(i>=width*height)return;
    int x=i%width,y=i/width;
    float center=input[i],sum=0,correction=0;
    for(int delta=-int(radius);delta<=int(radius);delta++) {
        int sx=axis==1 ? clamp(x+delta,0,int(width)-1):x;
        int sy=axis==0 ? clamp(y+delta,0,int(height)-1):y;
        float term=(input[sy*width+sx]-center)*weights[delta+int(radius)]-correction;
        float next=sum+term;
        correction=(next-sum)-term;
        sum=next;
    }
    output[i]=center+(sum-correction);
}
