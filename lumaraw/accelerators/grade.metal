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
float point_curve(float v,constant float *p,int start,int count){
    if(v<=p[start])return p[start+5];
    for(int i=1;i<count;i++){
        int next=start+6*i;
        if(v<=p[next]){
            int k=next-6;float t=clamp((v-p[k])/p[k+1],0.0f,1.0f);
            return clamp(((p[k+2]*t+p[k+3])*t+p[k+4])*t+p[k+5],0.0f,1.0f);
        }
    }
    return p[start+6*(count-1)+5];
}
float parametric_curve(float value,constant float *p){
    for(int region=0;region<4;region++){
        int k=592+4*region;
        if(p[k+3]==0)continue;
        float t=value<=p[k+1]?(value-p[k])/(p[k+1]-p[k]):(p[k+2]-value)/(p[k+2]-p[k+1]);
        t=clamp(t,0.0f,1.0f);
        value+=p[k+3]*t*t*(3.0f-2.0f*t);
    }
    return value;
}
float3 cuberoot(float3 x){
    float3 a=abs(x),root=pow(a,float3(1.0f/3.0f));
    // Compensated Newton residual corrects pow before subtractive Oklab matrices.
    // Include the rounded square's error and keep zero/negative inputs finite.
    float3 square=root*root,error=fma(root,root,-square);
    float3 residual=fma(-root,square,a)-root*error;
    root+=residual/max(3.0f*square,float3(1e-30f));
    return sign(x)*root;
}
float3 lab_from_work(float3 a,constant float *p){return mat(cuberoot(mat(mat(a,p,120),p,129)),p,138);}
float hue(float3 lab){float h=atan2(lab.z,lab.y)*57.29577951308232f;return h<0?h+360.0f:h;}
float mixer_weight(float h,float center){
    float d=fmod(h-center+180.0f,360.0f);if(d<0)d+=360.0f;d-=180.0f;
    float weight=max(0.0f,1.0f-abs(d)/50.0f);return weight*weight;
}
float mixer_neutral_weight(float3 lab){return min(1.0f,max(0.0f,length(lab.yz)-abs(lab.x)*1e-5f)/(abs(lab.x)*.1f+1e-7f));}
kernel void grade_output(device const float *input [[buffer(0)]],device float *output [[buffer(1)]],
                         device uchar *gamut [[buffer(2)]],constant float *p [[buffer(3)]],
                         constant uint &count [[buffer(4)]],uint i [[thread_position_in_grid]]) {
    if(i>=count)return;
    float3 a=float3(input[3*i],input[3*i+1],input[3*i+2]);
    float3 L=float3(p[12],p[13],p[14]);
    if(p[0]==0){
        const float centers[8]={29,65,109,142,195,264,305,342};
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
        if(p[53]!=0){
            float curveLum=dot(a,L);
            if(curveLum>0 && curveLum<1){
                float encoded=enc(curveLum),mapped=parametric_curve(encoded,p);
                if(mapped!=encoded)a*=dec(mapped)/curveLum;
            }
        }
        for(int channel=0;channel<3;channel++){
            if(p[49]==0 && p[50+channel]==0)continue;
            float value=enc(a[channel]);
            if(p[49]!=0)value=point_curve(value,p,208,int(p[49]));
            if(p[50+channel]!=0)value=point_curve(value,p,304+channel*96,int(p[50+channel]));
            a[channel]=dec(value);
        }
        if(p[39]!=0){
            float3 lab=lab_from_work(a,p);
            float h=hue(lab),chroma=length(lab.yz),dh=0,ds=0,dl=0;
            float neutral=mixer_neutral_weight(lab);
            for(int b=0;b<8;b++){
                int k=176+b*4;
                if(p[k]==0 && p[k+1]==0 && p[k+2]==0)continue;
                float w=mixer_weight(h,centers[b]);dh+=w*p[k];ds+=w*p[k+1]/100.0f;dl+=w*p[k+2]/100.0f;
            }
            float angle=(h+dh)*.017453292519943295f;chroma*=max(0.0f,1.0f+ds);
            lab.y=chroma*cos(angle);lab.z=chroma*sin(angle);
            float3 lms=mat(lab,p,147);float3 rgb=mat(lms*lms*lms,p,156);a=mat(rgb,p,165);
            a*=exp2(dl*2.0f*neutral);
        }
        if(p[9]!=0){
            float gray=dot(a,L);
            if(p[48]!=0){
                float3 lab=lab_from_work(a,p);float h=hue(lab),shift=0;
                float neutral=mixer_neutral_weight(lab);
                for(int b=0;b<8;b++){if(p[179+b*4]!=0)shift+=mixer_weight(h,centers[b])*p[179+b*4]/100.0f;}
                gray*=exp2(shift*2.0f*neutral);
            }
            a=float3(gray);
        }
    }
    float3 linear=mat(a,p,28);
    gamut[i]=any(linear<float3(-1e-5f)) || any(linear>float3(1.00001f));
    output[3*i]=enc(linear.x,int(p[38]));output[3*i+1]=enc(linear.y,int(p[38]));output[3*i+2]=enc(linear.z,int(p[38]));
}
