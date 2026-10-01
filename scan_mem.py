"""扫描目标进程内存中的 WorkBuddy at-rest 密钥 payload。
用法: python scan_mem.py <期望keyId> <pid> [<pid>...]
在可读内存区里找 "atRestSecretKey":"<base64>" 的 JSON 字面量（UTF-8 与 UTF-16LE），
候选 secret 用 sha256 推导 keyId，与期望 keyId 比对；命中则写 wb-key-payload.json。
"""
import ctypes, ctypes.wintypes as wt, json, os, re, sys, hashlib

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]

def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]

def verify(secret_b64):
    key = hashlib.sha256(secret_b64.encode()).digest()
    return key, hashlib.sha256(key).hexdigest()[:16]

def scan_pid(pid, expect_kid, found):
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("PID %d: OpenProcess 失败 err=%d" % (pid, ctypes.get_last_error()))
        return
    addr = 0
    total = 0
    while True:
        mbi = MBI()
        r = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not r:
            break
        base = mbi.BaseAddress if mbi.BaseAddress is not None else 0
        size = mbi.RegionSize or 0x1000
        if mbi.State == MEM_COMMIT and mbi.Protect != PAGE_NOACCESS and not (mbi.Protect & PAGE_GUARD):
            data = read_mem(h, base, size)
            if data:
                total += len(data)
                pat8 = re.compile(rb'"atRestSecretKey"\s*:\s*"([A-Za-z0-9+/]{43}=|[A-Za-z0-9+/]{44})"')
                pat16 = re.compile(rb'(?s)"\x00a\x00t\x00R\x00e\x00s\x00t\x00S\x00e\x00c\x00r\x00e\x00t\x00K\x00e\x00y\x00"\x00:\x00"\x00'
                                   rb'((?:[A-Za-z0-9+/]\x00){43}=\x00|(?:[A-Za-z0-9+/]\x00){44})')
                for pat, enc in ((pat8, "utf8"), (pat16, "utf16")):
                    for m in pat.finditer(data):
                        secret = m.group(1).decode("latin1").replace("\x00", "")
                        key, kid = verify(secret)
                        print("PID %d: 命中(%s) 推导keyId=%s %s" % (pid, enc, kid, "匹配" if kid == expect_kid else "不匹配"))
                        if kid == expect_kid:
                            found.append({"keyId": kid, "keyHex": key.hex()})
        addr = base + size
        if addr > 0x7FFFFFFEFFFF:
            break
    k32.CloseHandle(h)
    print("PID %d: 扫描完成, 可读内存 %.0f MB" % (pid, total / 1048576))

def main():
    expect = sys.argv[1]
    found = []
    for a in sys.argv[2:]:
        scan_pid(int(a), expect, found)
    if found:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wb-key-payload.json")
        with open(out, "w") as f:
            json.dump(found[0], f, indent=1)
        print("[OK] 已写入", out)
    else:
        print("[X] 未找到匹配的密钥 payload")

if __name__ == "__main__":
    main()
