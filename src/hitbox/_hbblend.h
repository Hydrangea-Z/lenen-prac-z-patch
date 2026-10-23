#ifndef HB_BLEND_H
#define HB_BLEND_H
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <string.h>
#include <stddef.h>

struct HBVertex { float pos[2],q0[4],q1[4],style[4]; };
template<class T> static void hb_release(T*& p) {if(p){p->Release();p=0;}}

// Snapshot every slot changed by this renderer; references are frame-scoped.
struct HBState {
    ID3D11DeviceContext* c;
    ID3D11RenderTargetView* rt[8]; ID3D11DepthStencilView* dsv;
    ID3D11UnorderedAccessView* uav[8];UINT nrt;
    ID3D11BlendState* blend;float factors[4];UINT mask;
    ID3D11DepthStencilState* depth;UINT ref;
    ID3D11RasterizerState* raster;D3D11_VIEWPORT vp[16];UINT nvp;
    ID3D11InputLayout* layout;ID3D11Buffer* vb;UINT stride,offset;
    D3D11_PRIMITIVE_TOPOLOGY topology;
    ID3D11VertexShader* vs;ID3D11PixelShader* ps;ID3D11GeometryShader* gs;
    ID3D11HullShader* hs;ID3D11DomainShader* ds;
    ID3D11ClassInstance* vc[256];ID3D11ClassInstance* pc[256];ID3D11ClassInstance* gc[256];
    ID3D11ClassInstance* hc[256];ID3D11ClassInstance* dc[256];UINT nv,np,ng,nh,nd;
    ID3D11ShaderResourceView* srv;ID3D11Predicate* predicate;BOOL pred_value;
    HBState(ID3D11DeviceContext* ctx):c(ctx) {
        memset(rt,0,sizeof(rt));memset(vc,0,sizeof(vc));memset(pc,0,sizeof(pc));memset(gc,0,sizeof(gc));memset(hc,0,sizeof(hc));memset(dc,0,sizeof(dc));
        nvp=16;nv=np=ng=nh=nd=256;
        memset(uav,0,sizeof(uav));
        c->OMGetRenderTargetsAndUnorderedAccessViews(8,rt,&dsv,0,8,uav);
        nrt=0;for(unsigned i=0;i<8;i++)if(rt[i])nrt=i+1;
        c->OMGetBlendState(&blend,factors,&mask);c->OMGetDepthStencilState(&depth,&ref);
        c->RSGetState(&raster);c->RSGetViewports(&nvp,vp);c->IAGetInputLayout(&layout);c->IAGetVertexBuffers(0,1,&vb,&stride,&offset);c->IAGetPrimitiveTopology(&topology);
        c->VSGetShader(&vs,vc,&nv);c->PSGetShader(&ps,pc,&np);c->GSGetShader(&gs,gc,&ng);c->HSGetShader(&hs,hc,&nh);c->DSGetShader(&ds,dc,&nd);
        c->PSGetShaderResources(0,1,&srv);c->GetPredication(&predicate,&pred_value);
    }
    ~HBState() {
        ID3D11ShaderResourceView* nil=0;c->PSSetShaderResources(0,1,&nil);
        UINT counts[8]={~0u,~0u,~0u,~0u,~0u,~0u,~0u,~0u};
        if(nrt<8)c->OMSetRenderTargetsAndUnorderedAccessViews(nrt,rt,dsv,nrt,8-nrt,uav+nrt,counts+nrt);
        else c->OMSetRenderTargets(8,rt,dsv);
        c->OMSetBlendState(blend,factors,mask);c->OMSetDepthStencilState(depth,ref);
        c->RSSetState(raster);c->RSSetViewports(nvp,vp);c->IASetInputLayout(layout);c->IASetVertexBuffers(0,1,&vb,&stride,&offset);c->IASetPrimitiveTopology(topology);
        c->VSSetShader(vs,vc,nv);c->PSSetShader(ps,pc,np);c->GSSetShader(gs,gc,ng);c->HSSetShader(hs,hc,nh);c->DSSetShader(ds,dc,nd);
        c->PSSetShaderResources(0,1,&srv);c->SetPredication(predicate,pred_value);
        for(unsigned i=0;i<8;i++){hb_release(rt[i]);hb_release(uav[i]);}hb_release(dsv);hb_release(blend);hb_release(depth);hb_release(raster);hb_release(layout);hb_release(vb);
        hb_release(vs);hb_release(ps);hb_release(gs);hb_release(hs);hb_release(ds);hb_release(srv);hb_release(predicate);
        for(unsigned i=0;i<nv;i++)hb_release(vc[i]);for(unsigned i=0;i<np;i++)hb_release(pc[i]);for(unsigned i=0;i<ng;i++)hb_release(gc[i]);
        for(unsigned i=0;i<nh;i++)hb_release(hc[i]);for(unsigned i=0;i<nd;i++)hb_release(dc[i]);
    }
};

struct HBGPU {
    int error_stage;HRESULT last_hr;unsigned draw_calls;
    ID3D11Device* dev;ID3D11DeviceContext* ctx;
    ID3D11VertexShader* shape_vs;ID3D11PixelShader* shape_ps;
    ID3D11VertexShader* full_vs;ID3D11PixelShader* full_ps;
    ID3D11InputLayout* layout;ID3D11Buffer* vb;unsigned capacity;
    ID3D11BlendState* max_blend;ID3D11BlendState* alpha_blend;
    ID3D11DepthStencilState* depth;ID3D11RasterizerState* raster;
    ID3D11Texture2D* overlay;ID3D11RenderTargetView* overlay_rt;ID3D11ShaderResourceView* overlay_srv;
    unsigned width,height;HMODULE compiler;
    HBGPU():error_stage(0),last_hr(S_OK),draw_calls(0),dev(0),ctx(0),shape_vs(0),shape_ps(0),full_vs(0),full_ps(0),layout(0),vb(0),capacity(0),max_blend(0),alpha_blend(0),depth(0),raster(0),overlay(0),overlay_rt(0),overlay_srv(0),width(0),height(0),compiler(0){}
    ~HBGPU(){cleanup();if(compiler)FreeLibrary(compiler);}
    void cleanup_size() {hb_release(overlay_srv);hb_release(overlay_rt);hb_release(overlay);width=height=0;}
    void cleanup() {
        cleanup_size();hb_release(shape_vs);hb_release(shape_ps);hb_release(full_vs);hb_release(full_ps);hb_release(layout);hb_release(vb);capacity=0;
        hb_release(max_blend);hb_release(alpha_blend);hb_release(depth);hb_release(raster);hb_release(ctx);hb_release(dev);
    }
    bool fail(int stage,HRESULT hr){error_stage=stage;last_hr=hr;return false;}
    bool compile(const char* code,const char* entry,const char* profile,ID3DBlob** blob) {
        if(!compiler) {
            WCHAR path[MAX_PATH];UINT n=GetSystemDirectoryW(path,MAX_PATH);
            if(!n || n+24>=MAX_PATH) return fail(1,HRESULT_FROM_WIN32(GetLastError()));
            wcscat(path,L"\\d3dcompiler_47.dll");compiler=LoadLibraryW(path);
            if(!compiler) return fail(1,HRESULT_FROM_WIN32(GetLastError()));
        }
        typedef HRESULT (WINAPI* Compile)(LPCVOID,SIZE_T,LPCSTR,const D3D_SHADER_MACRO*,ID3DInclude*,LPCSTR,LPCSTR,UINT,UINT,ID3DBlob**,ID3DBlob**);
        Compile fn=(Compile)GetProcAddress(compiler,"D3DCompile");if(!fn)return fail(1,E_NOINTERFACE);
        ID3DBlob* errors=0;HRESULT hr=fn(code,strlen(code),"hitbox-v10",0,0,entry,profile,D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_OPTIMIZATION_LEVEL3,0,blob,&errors);
        hb_release(errors);if(FAILED(hr))return fail(2,hr);return true;
    }
    bool setup_device(ID3D11Device* d) {
        cleanup();dev=d;dev->AddRef();dev->GetImmediateContext(&ctx);
        const char* shader=R"HB(
struct In {float2 p:POSITION;float4 q0:TEXCOORD0;float4 q1:TEXCOORD1;float4 style:TEXCOORD2;};
struct Out {float4 p:SV_POSITION;nointerpolation float4 q0:TEXCOORD0;nointerpolation float4 q1:TEXCOORD1;nointerpolation float4 style:TEXCOORD2;};
Out shapeVS(In v){Out o;o.p=float4(v.p,0,1);o.q0=v.q0;o.q1=v.q1;o.style=v.style;return o;}
float seg(float2 p,float2 a,float2 b){float2 e=b-a;float t=saturate(dot(p-a,e)/max(dot(e,e),1e-10));return length(p-a-e*t);}
float cross2(float2 a,float2 b){return a.x*b.y-a.y*b.x;}
float quadDist(float2 p,float4 q0,float4 q1){
 float2 a=q0.xy,b=q0.zw,c=q1.xy,d=q1.zw;
 float e=min(min(seg(p,a,b),seg(p,b,c)),min(seg(p,c,d),seg(p,d,a)));
 float4 side=float4(cross2(b-a,p-a),cross2(c-b,p-b),cross2(d-c,p-c),cross2(a-d,p-d));
 bool inside=all(side>=0)||all(side<=0);return inside?-e:e;
}
float4 shapePS(Out o):SV_TARGET{
 float2 p=o.p.xy;float dist;
 if(o.style.x<0.5 || o.style.x>1.5){
  float2 r=max(o.q0.zw,float2(0.001,0.001));float2 u=(p-o.q0.xy)/r;
  float k=length(u);float grad=length(u/r)/max(k,1e-6);
  dist=(k-1)/max(grad,1/max(r.x,r.y));
 }else dist=quadDist(p,o.q0,o.q1);
 float aa=0.7;float edge=1-smoothstep(o.style.y*0.5-aa,o.style.y*0.5+aa,abs(dist));
 float fill=(1-smoothstep(-aa,aa,dist))*(1-edge);
 float a=saturate(edge*o.style.w+fill*o.style.z);
 float3 edgeRGB=o.style.x>1.5?float3(1.0,0.82,0.35):float3(0.86,0.70,1.0);
 float3 fillRGB=o.style.x>1.5?float3(1.0,0.83,0.46):float3(0.80,0.70,1.0);
 float3 rgb=edgeRGB*(edge*o.style.w)+fillRGB*(fill*o.style.z);
 return float4(rgb,a);
}
float4 fullVS(uint id:SV_VertexID):SV_POSITION{
 float2 uv=float2((id<<1)&2,id&2);return float4(uv*float2(2,-2)+float2(-1,1),0,1);
}
Texture2D<float4> overlayTexture:register(t0);
float4 fullPS(float4 p:SV_POSITION):SV_TARGET{return overlayTexture.Load(int3(int2(p.xy),0));}
)HB";
        ID3DBlob *sv=0,*sp=0,*fv=0,*fp=0;
        bool good=compile(shader,"shapeVS","vs_4_0",&sv)&&compile(shader,"shapePS","ps_4_0",&sp)&&compile(shader,"fullVS","vs_4_0",&fv)&&compile(shader,"fullPS","ps_4_0",&fp);
        HRESULT hr=S_OK;
        if(good) {
            hr=dev->CreateVertexShader(sv->GetBufferPointer(),sv->GetBufferSize(),0,&shape_vs);
            if(SUCCEEDED(hr))hr=dev->CreatePixelShader(sp->GetBufferPointer(),sp->GetBufferSize(),0,&shape_ps);
            if(SUCCEEDED(hr))hr=dev->CreateVertexShader(fv->GetBufferPointer(),fv->GetBufferSize(),0,&full_vs);
            if(SUCCEEDED(hr))hr=dev->CreatePixelShader(fp->GetBufferPointer(),fp->GetBufferSize(),0,&full_ps);
            D3D11_INPUT_ELEMENT_DESC il[]={
                {"POSITION",0,DXGI_FORMAT_R32G32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"TEXCOORD",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,8,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"TEXCOORD",1,DXGI_FORMAT_R32G32B32A32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"TEXCOORD",2,DXGI_FORMAT_R32G32B32A32_FLOAT,0,40,D3D11_INPUT_PER_VERTEX_DATA,0}};
            if(SUCCEEDED(hr))hr=dev->CreateInputLayout(il,4,sv->GetBufferPointer(),sv->GetBufferSize(),&layout);
            good=SUCCEEDED(hr);if(!good)fail(3,hr);
        }
        hb_release(sv);hb_release(sp);hb_release(fv);hb_release(fp);
        if(!good){cleanup();return false;}
        D3D11_BLEND_DESC bd={};bd.RenderTarget[0].BlendEnable=TRUE;
        bd.RenderTarget[0].SrcBlend=bd.RenderTarget[0].DestBlend=D3D11_BLEND_ONE;bd.RenderTarget[0].BlendOp=D3D11_BLEND_OP_MAX;
        bd.RenderTarget[0].SrcBlendAlpha=bd.RenderTarget[0].DestBlendAlpha=D3D11_BLEND_ONE;bd.RenderTarget[0].BlendOpAlpha=D3D11_BLEND_OP_MAX;bd.RenderTarget[0].RenderTargetWriteMask=15;
        hr=dev->CreateBlendState(&bd,&max_blend);
        bd.RenderTarget[0].DestBlend=bd.RenderTarget[0].DestBlendAlpha=D3D11_BLEND_INV_SRC_ALPHA;
        bd.RenderTarget[0].BlendOp=bd.RenderTarget[0].BlendOpAlpha=D3D11_BLEND_OP_ADD;
        if(SUCCEEDED(hr))hr=dev->CreateBlendState(&bd,&alpha_blend);
        D3D11_DEPTH_STENCIL_DESC dd={};dd.DepthEnable=FALSE;dd.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;dd.DepthFunc=D3D11_COMPARISON_ALWAYS;
        if(SUCCEEDED(hr))hr=dev->CreateDepthStencilState(&dd,&depth);
        D3D11_RASTERIZER_DESC rd={};rd.FillMode=D3D11_FILL_SOLID;rd.CullMode=D3D11_CULL_NONE;rd.DepthClipEnable=TRUE;
        if(SUCCEEDED(hr))hr=dev->CreateRasterizerState(&rd,&raster);
        if(FAILED(hr)){fail(4,hr);cleanup();return false;}return true;
    }
    bool setup_size(unsigned w,unsigned h) {
        cleanup_size();D3D11_TEXTURE2D_DESC td={};td.Width=w;td.Height=h;td.MipLevels=1;td.ArraySize=1;td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
        td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_DEFAULT;td.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
        HRESULT hr=dev->CreateTexture2D(&td,0,&overlay);
        if(SUCCEEDED(hr))hr=dev->CreateRenderTargetView(overlay,0,&overlay_rt);
        if(SUCCEEDED(hr))hr=dev->CreateShaderResourceView(overlay,0,&overlay_srv);
        if(FAILED(hr)){cleanup_size();return fail(5,hr);}width=w;height=h;return true;
    }
    bool render(ID3D11Texture2D* backbuf,const HBVertex* vertices,unsigned count) {
        draw_calls=0;error_stage=0;last_hr=S_OK;
        if(!backbuf || !vertices || count>98304 || count%6) return fail(6,E_INVALIDARG);
        if(!count)return true;
        D3D11_TEXTURE2D_DESC td;backbuf->GetDesc(&td);ID3D11Device* d=0;backbuf->GetDevice(&d);
        if(!d)return fail(6,E_FAIL);
        bool ok=true;if(d!=dev)ok=setup_device(d);hb_release(d);if(!ok)return false;
        if(td.Width!=width || td.Height!=height || !overlay) if(!setup_size(td.Width,td.Height))return false;
        if(count>capacity) {
            unsigned wanted=capacity?capacity:6144;while(wanted<count)wanted*=2;if(wanted>98304)wanted=98304;
            D3D11_BUFFER_DESC bd={};bd.ByteWidth=wanted*sizeof(HBVertex);bd.Usage=D3D11_USAGE_DYNAMIC;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;bd.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;
            ID3D11Buffer* next=0;HRESULT hr=dev->CreateBuffer(&bd,0,&next);if(FAILED(hr))return fail(7,hr);
            hb_release(vb);vb=next;capacity=wanted;
        }
        D3D11_MAPPED_SUBRESOURCE map;HRESULT hr=ctx->Map(vb,0,D3D11_MAP_WRITE_DISCARD,0,&map);if(FAILED(hr))return fail(8,hr);
        memcpy(map.pData,vertices,count*sizeof(HBVertex));ctx->Unmap(vb,0);
        ID3D11RenderTargetView* target=0;hr=dev->CreateRenderTargetView(backbuf,0,&target);if(FAILED(hr))return fail(9,hr);
        {
            HBState saved(ctx); // No failure exits after this point; RAII restores.
            float zero[4]={0,0,0,0};UINT stride=sizeof(HBVertex),offset=0;
            ID3D11ShaderResourceView* nil=0;ctx->PSSetShaderResources(0,1,&nil);
            ctx->SetPredication(0,FALSE);ctx->GSSetShader(0,0,0);ctx->HSSetShader(0,0,0);ctx->DSSetShader(0,0,0);
            ctx->RSSetState(raster);D3D11_VIEWPORT vp={0,0,(float)width,(float)height,0,1};ctx->RSSetViewports(1,&vp);
            ctx->OMSetDepthStencilState(depth,0);ctx->IASetInputLayout(layout);ctx->IASetVertexBuffers(0,1,&vb,&stride,&offset);ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            ctx->VSSetShader(shape_vs,0,0);ctx->PSSetShader(shape_ps,0,0);
            ctx->OMSetRenderTargets(1,&overlay_rt,0);ctx->ClearRenderTargetView(overlay_rt,zero);ctx->OMSetBlendState(max_blend,zero,0xFFFFFFFF);
            ctx->Draw(count,0);draw_calls++;
            ctx->OMSetRenderTargets(1,&target,0);ctx->OMSetBlendState(alpha_blend,zero,0xFFFFFFFF);
            ctx->IASetInputLayout(0);ID3D11Buffer* no_vb=0;UINT no_stride=0;ctx->IASetVertexBuffers(0,1,&no_vb,&no_stride,&offset);
            ctx->VSSetShader(full_vs,0,0);ctx->PSSetShader(full_ps,0,0);ctx->PSSetShaderResources(0,1,&overlay_srv);
            ctx->Draw(3,0);draw_calls++;
        }
        hb_release(target); // Never retain backbuffer references across ResizeBuffers.
        hr=dev->GetDeviceRemovedReason();if(FAILED(hr))return fail(10,hr);return true;
    }
};
#endif
