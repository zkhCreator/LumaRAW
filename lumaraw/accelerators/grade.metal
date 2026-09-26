// Purpose: fuse linear ProPhoto D65 grading and ICC output encoding per RGB pixel.
// Inputs mirror the CPU equations (FP32, fast math disabled); never decode RAW.
// Geometry, neighborhood filters, masks and LUTs remain separate CPU stages.
#include <metal_stdlib>
using namespace metal;
float3 mat(float3 v,constant float *p,int offset) {
    return float3(dot(v,float3(p[offset],p[offset+1],p[offset+2])),
                  dot(v,float3(p[offset+3],p[offset+4],p[offset+5])),
                  dot(v,float3(p[offset+6],p[offset+7],p[offset+8])));
}
float enc(float v,int space=0){v=clamp(v,0.0f,1.0f);if(space==1)return pow(v,256.0f/563.0f);if(space==3)return v<1.0f/512.0f?v*16.0f:pow(v,1.0f/1.8f);return v<=.0031308f?v*12.92f:1.055f*pow(v,1.0f/2.4f)-.055f;}
float dec(float v){v=max(v,0.0f);return v<=.04045f?v/12.92f:pow((v+.055f)/1.055f,2.4f);}
float interpolate(float v,constant float *p,int start,int count){
    if(v<=p[start])return p[start+1];
    for(int i=1;i<count;i++){int j=start+2*i;if(v<=p[j]){float t=(v-p[j-2])/(p[j]-p[j-2]);return p[j-1]+t*(p[j+1]-p[j-1]);}}
    return p[start+2*count-1];
}
float3 cuberoot(float3 x){return sign(x)*pow(abs(x),float3(1.0f/3.0f));}
kernel void grade_output(device const float *input [[buffer(0)]],device float *output [[buffer(1)]],
                         device uchar *gamut [[buffer(2)]],constant float *p [[buffer(3)]],
                         constant uint &count [[buffer(4)]],uint i [[thread_position_in_grid]]) {
    if(i>=count)return;
    float3 a=float3(input[3*i],input[3*i+1],input[3*i+2]);
    float3 L=float3(p[12],p[13],p[14]);
    if(p[0]==0){
        a=mat(a,p,16)*p[1];
        float lum=max(dot(a,L),1e-7f),shadow=exp(-lum/.16f),light=lum/(lum+.35f);
        a*=exp2(p[2]*shadow*1.5f+p[3]*light*1.5f+p[4]*exp(-lum/.045f)+p[5]*pow(light,4.0f));
        lum=max(dot(a,L),1e-7f);
        if(p[6]!=0){float target=.18f*pow(lum/.18f,1.0f+p[6]);a*=target/lum;lum=target;}
        float mx=max(a.x,max(a.y,a.z)),mn=min(a.x,min(a.y,a.z));
        float spread=max(mx-mn,0.0f)/max(mx,1e-7f);
        float sat=p[7]*(1.0f+p[8]*(1.0f-min(spread,1.0f)));
        a=lum+(a-lum)*sat;
        if(p[10]!=0 || p[11]!=0){
            float v=enc(lum);
            if(p[10]!=0)v=interpolate(v,p,64,5);
            if(p[11]!=0)v=interpolate(v,p,80,int(p[11]));
            a*=dec(v)/lum;
        }
        if(p[39]!=0){
            float3 rgb=mat(a,p,120);
            float3 lms=mat(rgb,p,129);
            float3 lab=mat(cuberoot(lms),p,138);
            float h=atan2(lab.z,lab.y)*180.0f/M_PI_F;if(h<0)h+=360.0f;
            float chroma=length(lab.yz),dh=0,ds=0;
            const float centers[4]={29,65,142,264};
            for(int b=0;b<4;b++){float delta=fmod(h-centers[b]+540.0f,360.0f)-180.0f;float w=pow(max(0.0f,1.0f-abs(delta)/50.0f),2.0f);dh+=w*p[40+b*2];ds+=w*p[41+b*2];}
            float angle=(h+dh)*M_PI_F/180.0f;chroma*=max(0.0f,1.0f+ds);
            lab.y=chroma*cos(angle);lab.z=chroma*sin(angle);
            lms=mat(lab,p,147);rgb=mat(lms*lms*lms,p,156);a=mat(rgb,p,165);
        }
        if(p[9]!=0)a=float3(dot(a,L));
    }
    float3 linear=mat(a,p,28);
    gamut[i]=any(linear<float3(-1e-5f)) || any(linear>float3(1.00001f));
    output[3*i]=enc(linear.x,int(p[38]));output[3*i+1]=enc(linear.y,int(p[38]));output[3*i+2]=enc(linear.z,int(p[38]));
}
