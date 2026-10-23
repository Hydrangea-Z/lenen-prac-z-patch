// Le01 hitbox overlay v1: read-only geometry, batched GPU alpha blend.
// No collision writes, centre markers, or guessed capsule geometry.
// Le01 collision consumers: 0x4CDF80 dispatcher (stage in ECX), enemy bullets
// 0x4CE7C9.., lasers 0x4CECC6.., boss contact 0x4CF5D3/0x4CFC51 (secondary uses
// the PRIMARY body's +0x54 phase). Radius is the manager table entry alone;
// there is NO per-bullet scale multiplication (descriptor 0x432A81/0x432A89).
#include <windows.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "_hbblend.h"

struct HBCTX {
    unsigned stage;   // +00 current stage (collision dispatcher ECX)
    unsigned texture; // +04 scene texture (ID3D11Texture2D*)
    int cw, ch;       // +08 +0C scene texture size
    float ox, oy;     // +10 +14 logical playfield origin
    float lw, lh;     // +18 +1C logical canvas
    int devmode;      // +20
};
static_assert(sizeof(void*)==4 && sizeof(HBCTX)==0x24,"32-bit Le01 HBCTX ABI");

static const unsigned MAX_SLOTS=4096, MAX_SHAPES=16384, TABLE_N=50;
static HBVertex g_vertices[MAX_SHAPES*6];
static unsigned g_count=0;
static HBGPU g_gpu;

struct HBStats {
    unsigned version, frames, bullets, lasers, vertices, draw_calls;
    unsigned unreadable, noncollision, invalid, offscreen, capacity;
    unsigned gpu_stage, gpu_hr;
    unsigned bosses;
};
static HBStats g_stats={1};
extern "C" __declspec(dllexport) const HBStats* __cdecl hb_stats() { return &g_stats; }

struct HBCFG {
    float global_scale;
    unsigned char has[TABLE_N];
    float r[TABLE_N];
    float stroke, fill_alpha, edge_alpha;
};
static HBCFG g_cfg;
static unsigned g_cfg_stage=0;

static bool read_mem(unsigned a, void* out, unsigned n)
{
    if (a<0x10000 || a>=0x7FFF0000 || n>0x7FFF0000-a) return false;
    SIZE_T got=0;
    return ReadProcessMemory(GetCurrentProcess(),(const void*)a,out,n,&got) && got==n;
}
static unsigned read_u(unsigned a)
{
    unsigned v=0;
    return read_mem(a,&v,sizeof(v)) ? v : 0;
}
static float sane(float v,float lo,float hi,float fallback)
{
    return isfinite(v) && v>=lo && v<=hi ? v : fallback;
}
static void cfg_load()
{
    memset(&g_cfg,0,sizeof(g_cfg));
    g_cfg.global_scale=1.0f;
    g_cfg.stroke=1.25f; g_cfg.fill_alpha=0.10f; g_cfg.edge_alpha=0.95f;
    FILE* f=fopen("Le01hitbox-v1.ini","r");
    if (!f) return;
    char line[256]; int section=0;
    while (fgets(line,sizeof(line),f)) {
        char* p=line; while (*p==' ' || *p=='\t') p++;
        if (!*p || *p==';' || *p=='#') continue;
        if (*p=='[') {
            section=!_strnicmp(p+1,"radius",6)?1:(!_strnicmp(p+1,"style",5)?2:0);
            continue;
        }
        char* eq=strchr(p,'='); if (!eq) continue;
        *eq=0; char* end=eq; while(end>p && (end[-1]==' ' || end[-1]=='\t')) *--end=0;
        float v=(float)atof(eq+1);
        if(section==1) {
            if(!_stricmp(p,"global")) g_cfg.global_scale=sane(v,0.01f,100.0f,1.0f);
            else {
                char* num_end=0; unsigned t=(unsigned)strtoul(p,&num_end,0);
                if(num_end!=p && !*num_end && t<TABLE_N && isfinite(v) && v>0 && v<=1000) {g_cfg.has[t]=1;g_cfg.r[t]=v;}
            }
        } else if(section==2) {
            if(!_stricmp(p,"stroke_px")) g_cfg.stroke=sane(v,0.5f,4.0f,1.25f);
            else if(!_stricmp(p,"fill_alpha")) g_cfg.fill_alpha=sane(v,0.0f,0.25f,0.10f);
            else if(!_stricmp(p,"edge_alpha")) g_cfg.edge_alpha=sane(v,0.1f,1.0f,0.95f);
        }
    }
    fclose(f);
}
static bool finite_xy(float x,float y)
{
    return isfinite(x) && isfinite(y) && fabsf(x)<100000.0f && fabsf(y)<100000.0f;
}
static bool add_shape(HBCTX* c, float l,float t,float r,float b,
                      const float q0[4],const float q1[4],float kind)
{
    float pad=g_cfg.stroke*0.5f+1.0f;
    l-=pad; t-=pad; r+=pad; b+=pad;
    if(r<0 || b<0 || l>c->cw || t>c->ch) {g_stats.offscreen++;return false;}
    l=fmaxf(0,l);t=fmaxf(0,t);r=fminf((float)c->cw,r);b=fminf((float)c->ch,b);
    if(r<=l || b<=t) {g_stats.invalid++;return false;}
    if(g_count/6>=MAX_SHAPES) {g_stats.capacity++;return false;}
    float x[6]={l,r,l,l,r,r}, y[6]={t,t,b,b,t,b};
    for(unsigned k=0;k<6;k++) {
        HBVertex& v=g_vertices[g_count++];
        v.pos[0]=x[k]*2.0f/c->cw-1.0f; v.pos[1]=1.0f-y[k]*2.0f/c->ch;
        memcpy(v.q0,q0,16);memcpy(v.q1,q1,16);
        v.style[0]=kind;v.style[1]=g_cfg.stroke;
        v.style[2]=g_cfg.fill_alpha;v.style[3]=g_cfg.edge_alpha;
    }
    return true;
}
// Logical playfield coordinates -> scene-texture pixels. The game's own final
// compositor consumes this texture, so no window/backbuffer guesswork is needed.
// The game scales the 640x480 logical canvas UNIFORMLY and centres it in the
// client (letterbox bars), so the overlay must do the same. Using cw/640 for x
// alone stretched the shapes and pushed them left of the real content.
static void canvas_map(const HBCTX* c,float& s,float& offx,float& offy)
{
    float sx=(float)c->cw/c->lw, sy=(float)c->ch/c->lh;
    s=sx<sy?sx:sy;
    offx=((float)c->cw-c->lw*s)*0.5f;
    offy=((float)c->ch-c->lh*s)*0.5f;
}
static bool add_circle(HBCTX* c,float fx,float fy,float radius,float kind=0)
{
    float s,offx,offy;canvas_map(c,s,offx,offy);
    float x=offx+(fx+c->ox)*s, y=offy+(fy+c->oy)*s;
    float rx=radius*s, ry=radius*s;
    if(!finite_xy(x,y) || !isfinite(rx) || !isfinite(ry) || rx<=0 || ry<=0) {g_stats.invalid++;return false;}
    float q0[4]={x,y,rx,ry},q1[4]={0,0,0,0};
    return add_shape(c,x-rx,y-ry,x+rx,y+ry,q0,q1,kind);
}
static bool add_quad(HBCTX* c,const float xy[8])
{
    float s,offx,offy;canvas_map(c,s,offx,offy);
    float q[8],l=1e20f,t=1e20f,r=-1e20f,b=-1e20f;
    for(unsigned i=0;i<4;i++) {
        if(!finite_xy(xy[2*i],xy[2*i+1])) {g_stats.invalid++;return false;}
        float x=offx+(xy[2*i]+c->ox)*s, y=offy+(xy[2*i+1]+c->oy)*s;
        q[2*i]=x;q[2*i+1]=y;
        l=fminf(l,x);r=fmaxf(r,x);t=fminf(t,y);b=fmaxf(b,y);
    }
    return add_shape(c,l,t,r,b,q,q+4,1);
}
// Le02 vector layout: begin at +4, end at +8 (NOT +0/+4).
static unsigned read_vector(unsigned container,unsigned* dst)
{
    unsigned pair[2];
    if(!container || !read_mem(container+4,pair,8)) return 0;
    unsigned b=pair[0],e=pair[1];
    if(b<0x10000 || e<b || (b&3) || (e&3) || e-b>MAX_SLOTS*4) {g_stats.invalid++;return 0;}
    unsigned n=(e-b)/4;
    if(n && !read_mem(b,dst,n*4)) {g_stats.unreadable++;return 0;}
    return n;
}
// Inclusive high-water index at +0x20 (the dispatcher loops 0..hw).
static unsigned vector_limit(unsigned mgr,unsigned hw_off,unsigned n)
{
    unsigned hw=read_u(mgr+hw_off);
    if(hw==0xFFFFFFFFu || hw>=n) return n;
    return hw+1;
}
// Manager: +0x04/+0x08 vector of slot wrappers, +0x20 high-water,
// +0x24 radius table. Slot wrapper -> [slot] -> bullet.
static void collect_bullets(HBCTX* c,unsigned mgr)
{
    if(!mgr) return;
    float table[TABLE_N];
    if(!read_mem(mgr+0x24,table,sizeof(table))) {g_stats.unreadable++;return;}
    unsigned slots[MAX_SLOTS];
    unsigned n=read_vector(mgr,slots);
    if(!n) return;
    unsigned limit=vector_limit(mgr,0x20,n);
    for(unsigned i=0;i<limit;i++) {
        // Dispatcher 0x4C35D2: element -> [element] is the bullet (one deref).
        unsigned obj=read_u(slots[i]);
        unsigned char d[0x90];
        if(!read_mem(obj,d,sizeof(d))) {g_stats.unreadable++;continue;}
        int live; unsigned typ,pos; float xy[2];
        memcpy(&live,d+8,4);memcpy(&typ,d+0x44,4);memcpy(&pos,d,4);
        if(live<=0 || !d[0x83]) {g_stats.noncollision++;continue;}
        if(typ>=TABLE_N) {g_stats.invalid++;continue;}
        if(!read_mem(pos,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        float radius=table[typ]; // Le02: table only, no bullet scale
        if(g_cfg.has[typ]) radius=g_cfg.r[typ];
        radius*=g_cfg.global_scale;
        if(!finite_xy(xy[0],xy[1]) || !isfinite(radius) || radius<=0 || radius>10000) {g_stats.invalid++;continue;}
        if(add_circle(c,xy[0],xy[1],radius)) g_stats.bullets++;
    }
}
// Lasers: container vector of DIRECT laser pointers; +8==1, byte[+0x64]==1,
// four vertices at [laser+0x5C].
static void collect_lasers(HBCTX* c,unsigned container)
{
    if(!container) return;
    unsigned slots[MAX_SLOTS];
    unsigned n=read_vector(container,slots);
    if(!n) return;
    unsigned limit=vector_limit(container,0x10,n);
    for(unsigned i=0;i<limit;i++) {
        unsigned char d[0x68]; unsigned live,q;float xy[8];
        if(!read_mem(slots[i],d,sizeof(d))) {g_stats.unreadable++;continue;}
        memcpy(&live,d+8,4);memcpy(&q,d+0x5C,4);
        if(live!=1 || d[0x64]!=1) {g_stats.noncollision++;continue;}
        if(!read_mem(q,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        if(add_quad(c,xy)) g_stats.lasers++;
    }
}
// Boss: wrapper=[stage+8]; bodies at +0/+4; bullet manager +0xC; lasers +0x18.
// Both contacts require the PRIMARY body's +0x54==2 and each body's +8==1.
static void collect_bosses(HBCTX* c)
{
    unsigned wrapper=read_u(c->stage+8);
    if(!wrapper) return;
    unsigned bodies[2];
    if(!read_mem(wrapper,bodies,sizeof(bodies))) {g_stats.unreadable++;return;}
    if(!bodies[0]) return;
    unsigned phase=read_u(bodies[0]+0x54);
    if(phase!=2) {g_stats.noncollision++;return;}
    for(unsigned i=0;i<2;i++) {
        unsigned char d[0x3C];unsigned pos,live;float radius,xy[2];
        if(!bodies[i]) continue;
        if(!read_mem(bodies[i],d,sizeof(d))) {g_stats.unreadable++;continue;}
        memcpy(&pos,d,4);memcpy(&live,d+8,4);memcpy(&radius,d+0x38,4);
        if(live!=1) {g_stats.noncollision++;continue;}
        if(!isfinite(radius) || radius<=0 || radius>10000) {g_stats.invalid++;continue;}
        if(!read_mem(pos,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        if(add_circle(c,xy[0],xy[1],radius,2)) g_stats.bosses++;
    }
}
extern "C" __declspec(dllexport) int __cdecl hb_frame(HBCTX* c)
{
    unsigned frame=g_stats.frames+1;
    memset(&g_stats,0,sizeof(g_stats));g_stats.version=1;g_stats.frames=frame;
    g_count=0;
    if(!c || !c->texture || !c->stage) return 0;
    if(c->cw<16 || c->ch<16 || c->cw>16384 || c->ch>16384) {
        // The .cea passes 0x0 for Le01; resolve the real size from the texture.
        D3D11_TEXTURE2D_DESC td;
        ((ID3D11Texture2D*)c->texture)->GetDesc(&td);
        c->cw=(int)td.Width;c->ch=(int)td.Height;
        if(c->cw<16 || c->ch<16 || c->cw>16384 || c->ch>16384) return 0;
    }
    if(c->lw<16 || c->lh<16) return 0;
    if(c->stage!=g_cfg_stage) {cfg_load();g_cfg_stage=c->stage;}
    unsigned enemy=read_u(c->stage+4);
    if(enemy) {
        collect_bullets(c,read_u(enemy+0xC));
        collect_lasers(c,read_u(enemy+0x10));
    }
    unsigned boss=read_u(c->stage+8);
    if(boss) {
        collect_bullets(c,read_u(boss+0xC));
        collect_lasers(c,read_u(boss+0x18));
    }
    collect_bosses(c);
    g_stats.vertices=g_count;
    if(g_count) {
        bool ok=g_gpu.render((ID3D11Texture2D*)c->texture,g_vertices,g_count);
        g_stats.gpu_stage=g_gpu.error_stage;g_stats.gpu_hr=(unsigned)g_gpu.last_hr;
        g_stats.draw_calls=g_gpu.draw_calls;
        if(!ok) return 0;
    }
    return (int)(g_stats.bullets+g_stats.lasers+g_stats.bosses);
}
