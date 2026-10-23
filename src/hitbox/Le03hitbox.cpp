// Le03 hitbox overlay v10: read-only geometry, batched GPU alpha blend.
// No collision writes, centre markers, priority starvation, or opaque uploads.
// HBCTX ABI stays compatible with the practice stub. VAs apply to 1.21a base.
#include <windows.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "_hbblend.h"

struct HBCTX {
    unsigned barrage;
    void* update;
    unsigned* box;
    unsigned* dot;
    int sxp, syp, dx, dy, oxq, oyq, clw, clh;
    void* backbuf;
    int cap; // legacy ABI; NOT a render limit
};
static_assert(sizeof(void*)==4 && sizeof(HBCTX)==0x38,"32-bit HBCTX ABI must match the practice stub");
static const unsigned VT_E=0x868778, VT_B0=0x8673B8, VT_B1=0x8673B0;
static const unsigned MAX_SLOTS=4096, MAX_SHAPES=16384;
static HBVertex g_vertices[MAX_SHAPES*6];
static unsigned g_count=0;
static HBGPU g_gpu;

struct HBStats {
    unsigned version, frames, bullets, lasers, vertices, draw_calls;
    unsigned unreadable, noncollision, invalid, offscreen, capacity;
    unsigned gpu_stage, gpu_hr;
    unsigned bosses; // appended: original stats offsets remain unchanged
};
static HBStats g_stats={11};
extern "C" __declspec(dllexport) const HBStats* __cdecl hb_stats() { return &g_stats; }

struct HBCFG {
    float global_scale;
    unsigned char has[80];
    float r[80];
    float stroke, fill_alpha, edge_alpha;
    float origin_x, origin_y; // playfield origin in logical units
};
static HBCFG g_cfg;
static unsigned g_cfg_barrage=0;

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
    g_cfg.origin_x=32.0f; g_cfg.origin_y=16.0f;
    FILE* f=fopen("Le03hitbox-v11.ini","r");
    if (!f) return;
    char line[256]; int section=0;
    while (fgets(line,sizeof(line),f)) {
        char* p=line; while (*p==' ' || *p=='\t') p++;
        if (!*p || *p==';' || *p=='#') continue;
        if (*p=='[') {
            section=!_strnicmp(p+1,"radius",6)?1:(!_strnicmp(p+1,"style",5)?2:(!_strnicmp(p+1,"origin",6)?3:0));
            continue;
        }
        char* eq=strchr(p,'='); if (!eq) continue;
        *eq=0; char* end=eq; while(end>p && (end[-1]==' ' || end[-1]=='\t')) *--end=0;
        float v=(float)atof(eq+1);
        if(section==1) {
            if(!_stricmp(p,"global")) g_cfg.global_scale=sane(v,0.01f,100.0f,1.0f);
            else {
                char* num_end=0; unsigned t=(unsigned)strtoul(p,&num_end,0);
                if(num_end!=p && !*num_end && t<80 && isfinite(v) && v>0 && v<=1000) {g_cfg.has[t]=1;g_cfg.r[t]=v;}
            }
        } else if(section==2) {
            if(!_stricmp(p,"stroke_px")) g_cfg.stroke=sane(v,0.5f,4.0f,1.25f);
            else if(!_stricmp(p,"fill_alpha")) g_cfg.fill_alpha=sane(v,0.0f,0.25f,0.10f);
            else if(!_stricmp(p,"edge_alpha")) g_cfg.edge_alpha=sane(v,0.1f,1.0f,0.95f);
        } else if(section==3) {
            if(!_stricmp(p,"x")) g_cfg.origin_x=sane(v,-200.0f,200.0f,32.0f);
            else if(!_stricmp(p,"y")) g_cfg.origin_y=sane(v,-200.0f,200.0f,16.0f);
        }
    }
    fclose(f);
}
// The game scales the 640x480 logical canvas UNIFORMLY and centres it in the
// client (letterbox bars). The old per-axis formula baked in a 16:10 aspect
// (333/400) and an origin that folded the bar in as 96.75 instead of 96.0,
// which left a ~2 px offset even at 2560x1600.
static void canvas_map(const HBCTX* c,float& s,float& offx,float& offy)
{
    float sx=(float)c->clw/640.0f, sy=(float)c->clh/480.0f;
    s=sx<sy?sx:sy;
    offx=((float)c->clw-640.0f*s)*0.5f;
    offy=((float)c->clh-480.0f*s)*0.5f;
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
    if(r<0 || b<0 || l>c->clw || t>c->clh) {g_stats.offscreen++;return false;}
    l=fmaxf(0,l);t=fmaxf(0,t);r=fminf((float)c->clw,r);b=fminf((float)c->clh,b);
    if(r<=l || b<=t) {g_stats.invalid++;return false;}
    if(g_count/6>=MAX_SHAPES) {g_stats.capacity++;return false;}
    float x[6]={l,r,l,l,r,r}, y[6]={t,t,b,b,t,b};
    for(unsigned k=0;k<6;k++) {
        HBVertex& v=g_vertices[g_count++];
        v.pos[0]=x[k]*2.0f/c->clw-1.0f; v.pos[1]=1.0f-y[k]*2.0f/c->clh;
        memcpy(v.q0,q0,16);memcpy(v.q1,q1,16);
        v.style[0]=kind;v.style[1]=g_cfg.stroke;
        v.style[2]=g_cfg.fill_alpha;v.style[3]=g_cfg.edge_alpha;
    }
    return true;
}
static bool add_circle(HBCTX* c,float fx,float fy,float radius,float kind=0)
{
    float s,offx,offy;canvas_map(c,s,offx,offy);
    float x=offx+(fx+g_cfg.origin_x)*s,y=offy+(fy+g_cfg.origin_y)*s;
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
        float x=offx+(xy[2*i]+g_cfg.origin_x)*s,y=offy+(xy[2*i+1]+g_cfg.origin_y)*s;
        q[2*i]=x;q[2*i+1]=y;
        l=fminf(l,x);r=fmaxf(r,x);t=fminf(t,y);b=fmaxf(b,y);
    }
    return add_shape(c,l,t,r,b,q,q+4,1);
}
static unsigned resolve_mgr(unsigned field,const unsigned* vts,unsigned nvt)
{
    unsigned vt=read_u(field);
    for(unsigned i=0;i<nvt;i++) if(vt==vts[i]) return field;
    unsigned inner=read_u(field+0xC); vt=read_u(inner);
    for(unsigned i=0;i<nvt;i++) if(vt==vts[i]) return inner;
    return 0;
}
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
static void collect_bullets(HBCTX* c,unsigned off,const unsigned* vts,unsigned nvt)
{
    unsigned mgr=resolve_mgr(read_u(c->barrage+off),vts,nvt);
    if(!mgr) return;
    float table[80]; if(!read_mem(mgr+0x24,table,sizeof(table))) {g_stats.unreadable++;return;}
    unsigned slots[MAX_SLOTS];unsigned n=read_vector(mgr,slots);
    for(unsigned i=0;i<n;i++) {
        unsigned obj=read_u(slots[i]); unsigned char d[0x90];
        if(!read_mem(obj,d,sizeof(d))) {g_stats.unreadable++;continue;}
        unsigned live,typ,pos;float xy[2];double scale;
        memcpy(&live,d+8,4);memcpy(&typ,d+0x44,4);memcpy(&pos,d,4);memcpy(&scale,d+0x30,8);
        if(!live || !d[0x83]) {g_stats.noncollision++;continue;}
        if(typ>=80 || !isfinite(scale)) {g_stats.invalid++;continue;}
        if(!read_mem(pos,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        float radius=(float)scale*table[typ];
        if(g_cfg.has[typ]) radius=g_cfg.r[typ];
        radius*=g_cfg.global_scale;
        if(!finite_xy(xy[0],xy[1]) || !isfinite(radius) || radius<=0 || radius>10000) {g_stats.invalid++;continue;}
        if(add_circle(c,xy[0],xy[1],radius)) g_stats.bullets++;
    }
}
static void collect_lasers(HBCTX* c,unsigned off,unsigned laser_off,const unsigned* vts,unsigned nvt)
{
    unsigned wrapper=read_u(c->barrage+off);
    unsigned mgr=resolve_mgr(wrapper,vts,nvt);
    if(!mgr || mgr==wrapper) return;
    unsigned slots[MAX_SLOTS];unsigned n=read_vector(read_u(wrapper+laser_off),slots);
    for(unsigned i=0;i<n;i++) {
        unsigned char d[0x68]; unsigned live,q;float xy[8];
        if(!read_mem(slots[i],d,sizeof(d))) {g_stats.unreadable++;continue;}
        memcpy(&live,d+8,4);memcpy(&q,d+0x5C,4);
        if(live!=1 || d[0x64]!=1) {g_stats.noncollision++;continue;}
        if(!read_mem(q,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        if(add_quad(c,xy)) g_stats.lasers++;
    }
}
// Original contact dispatch VA 0x4EE90A / 0x4EEF06, descriptor 0x42F000.
// Wrapper owns two body objects at +0/+4; NOT the bullet manager at +0xC.
// Secondary body deliberately shares the PRIMARY body's +0x54 state gate.
static void collect_bosses(HBCTX* c)
{
    unsigned wrapper=read_u(c->barrage+8);
    unsigned vtB[]={VT_B0,VT_B1};
    unsigned mgr=resolve_mgr(wrapper,vtB,2);
    if(!mgr || mgr==wrapper) return;
    unsigned bodies[2];
    if(!read_mem(wrapper,bodies,sizeof(bodies))) {g_stats.unreadable++;return;}
    unsigned phase=0;
    if(!read_mem(bodies[0]+0x54,&phase,4)) {g_stats.unreadable++;return;}
    if(phase!=2) {g_stats.noncollision++;return;}
    for(unsigned i=0;i<2;i++) {
        unsigned char d[0x3C];unsigned pos,live;float radius,xy[2];
        if(!read_mem(bodies[i],d,sizeof(d))) {g_stats.unreadable++;continue;}
        memcpy(&pos,d,4);memcpy(&live,d+8,4);memcpy(&radius,d+0x38,4);
        if(live!=1) {g_stats.noncollision++;continue;}
        if(!isfinite(radius) || radius<=0 || radius>10000) {g_stats.invalid++;continue;}
        if(!read_mem(pos,xy,sizeof(xy))) {g_stats.unreadable++;continue;}
        // Draw the boss body itself, not radius+player radius (center-risk area).
        // Read current radius each frame; never invent sprite/animation scaling.
        if(add_circle(c,xy[0],xy[1],radius,2)) g_stats.bosses++;
    }
}
extern "C" __declspec(dllexport) int __cdecl hb_frame(HBCTX* c)
{
    unsigned frame=g_stats.frames+1;
    memset(&g_stats,0,sizeof(g_stats));g_stats.version=11;g_stats.frames=frame;
    g_count=0;
    if(!c || !c->backbuf || c->clw<16 || c->clh<16 || c->clw>16384 || c->clh>16384 || c->sxp<=0 || c->syp<=0) return 0;
    if(c->barrage!=g_cfg_barrage) {cfg_load();g_cfg_barrage=c->barrage;}
    unsigned vtE[]={VT_E},vtB[]={VT_B0,VT_B1};
    collect_bullets(c,4,vtE,1);collect_bullets(c,8,vtB,2);
    collect_lasers(c,4,0x10,vtE,1);collect_lasers(c,8,0x18,vtB,2);
    collect_bosses(c);
    g_stats.vertices=g_count;
    if(g_count) {
        // All probing is complete BEFORE changing render state. No longjmp.
        bool ok=g_gpu.render((ID3D11Texture2D*)c->backbuf,g_vertices,g_count);
        g_stats.gpu_stage=g_gpu.error_stage;g_stats.gpu_hr=(unsigned)g_gpu.last_hr;
        g_stats.draw_calls=g_gpu.draw_calls;
        if(!ok) return 0; // NEVER silently substitute dots
    }
    return (int)(g_stats.bullets+g_stats.lasers+g_stats.bosses);
}
