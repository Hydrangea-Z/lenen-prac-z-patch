// Le03speed.dll -- fullscreen acceleration for Le03, built the way leprac does it.
//
// Why a DLL: leprac's trick is to patch the *shared* IDXGISwapChain vtable, which
// is per-class, so one patch covers every swapchain in the process including the
// game's real one.  That needs a live swapchain to read the vtable from -- easy in
// C++, impossible to hand-write in asm.  So: create a tiny dummy device+swapchain,
// take its vtable, patch slot 8 (Present), throw the dummy away.
//
// The stub always passes syncInterval = 0.  The game's own frame limiter (the K
// constant the Speed row writes) then decides the rate, so Speed=60 still means
// 60fps and Speed=240 really means up to the monitor's refresh.
//
// d3d11.dll is resolved with GetProcAddress because this toolchain ships no
// libd3d11.a; only headers are needed, and all interface calls are virtual.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>

typedef HRESULT (WINAPI *PFN_CreateDeviceAndSwapChain)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*,
    UINT, UINT, const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**,
    ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

typedef HRESULT (WINAPI *PFN_Present)(IDXGISwapChain*, UINT, UINT);

static PFN_Present g_origPresent = 0;
static volatile LONG g_installed = 0;

// Whether Present should skip vsync.  The game exe flips this every frame from
// its speed row: vsync is only worth sacrificing when the target rate is above
// 60, otherwise it just tears the picture for no gain.  Defaults to 1 so builds
// that predate the switch keep accelerating.
__declspec(dllexport) volatile LONG g_noVsync = 1;

static HRESULT WINAPI HookPresent(IDXGISwapChain* sc, UINT sync, UINT flags)
{
    // 0 = present immediately; the game's limiter paces the loop instead.
    // Otherwise leave the game's own sync interval alone so vsync stays on.
    return g_origPresent(sc, g_noVsync ? 0 : sync, flags);
}

// Overwrite one vtable slot.  The page holding dxgi's vtables is read-only, so it
// has to be opened for writing first; the original entry is saved for the stub.
static int PatchSlot(void** vt, int slot, void* fn, void** orig)
{
    DWORD oldProt = 0;
    void** p = &vt[slot];
    if (!VirtualProtect(p, sizeof(void*), PAGE_EXECUTE_READWRITE, &oldProt))
        return 0;
    if (!*orig) *orig = *p;
    *p = fn;
    VirtualProtect(p, sizeof(void*), oldProt, &oldProt);
    return 1;
}

static LRESULT CALLBACK DummyProc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    return DefWindowProcW(h, m, w, l);
}

static DWORD WINAPI InitThread(LPVOID)
{
    // Let the game finish its own D3D setup first; patching later is fine because
    // the vtable is shared, so the game's existing swapchain picks it up too.
    Sleep(1200);

    HMODULE hD3D = LoadLibraryA("d3d11.dll");
    if (!hD3D) return 0;
    PFN_CreateDeviceAndSwapChain create =
        (PFN_CreateDeviceAndSwapChain)GetProcAddress(hD3D, "D3D11CreateDeviceAndSwapChain");
    if (!create) return 0;

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof wc);
    wc.cbSize = sizeof wc;
    wc.lpfnWndProc = DummyProc;
    wc.hInstance = GetModuleHandleW(0);
    wc.lpszClassName = L"Le03speedDummy";
    RegisterClassExW(&wc);

    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"", WS_OVERLAPPEDWINDOW,
                                0, 0, 16, 16, 0, 0, wc.hInstance, 0);

    DXGI_SWAP_CHAIN_DESC sd;
    ZeroMemory(&sd, sizeof sd);
    sd.BufferCount = 1;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow = hwnd;
    sd.SampleDesc.Count = 1;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    IDXGISwapChain* sc = 0;
    ID3D11Device* dev = 0;
    ID3D11DeviceContext* ctx = 0;

    HRESULT hr = create(0, D3D_DRIVER_TYPE_HARDWARE, 0, 0, 0, 0,
                        D3D11_SDK_VERSION, &sd, &sc, &dev, 0, &ctx);
    if (FAILED(hr)) {
        hr = create(0, D3D_DRIVER_TYPE_WARP, 0, 0, 0, 0,
                    D3D11_SDK_VERSION, &sd, &sc, &dev, 0, &ctx);
    }

    if (SUCCEEDED(hr) && sc) {
        void** vt = *(void***)sc;          // the shared IDXGISwapChain vtable
        if (PatchSlot(vt, 8, (void*)HookPresent, (void**)&g_origPresent))
            InterlockedExchange(&g_installed, 1);
    }

    if (ctx) ctx->Release();
    if (dev) dev->Release();
    if (sc) sc->Release();
    if (hwnd) DestroyWindow(hwnd);
    UnregisterClassW(wc.lpszClassName, wc.hInstance);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        CreateThread(0, 0, InitThread, 0, 0, 0);
    }
    return TRUE;
}

// Lets a test harness ask whether the patch went in.
__declspec(dllexport) int Le03speed_Installed(void)
{
    return (int)g_installed;
}
