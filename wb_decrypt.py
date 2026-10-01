"""验证 WorkBuddy 令牌信封解密链。
前置: scan_mem.py 已产出同目录 wb-key-payload.json（含 secretB64 或 keyHex）。
流程: sha256(secret) -> protector key -> AES-256-GCM 解开 auth 文件里 accessToken 信封
      （AAD 按 WB-AAD v1 规范构造，field/file 两种 framing 都试）。
输出: JWT 的 iss/sub 前8/exp（脱敏），不打印完整令牌。
"""
import base64, hashlib, json, os, sys, time

HOME = os.path.expanduser("~")
AUTH = HOME + "/AppData/Local/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info"
KEYBLOB = HOME + "/.workbuddy/keyblob"

def u32(n):
    return int(n).to_bytes(4, "big")

def lp(s):
    b = s.encode() if isinstance(s, str) else s
    return u32(len(b)) + b

def build_aad(key_id, framing):
    # sym-v1, whole-value context: 无 sequence(0x00)、final 未定义(0x00)
    names = {"file": ("WBEF1", 1), "field": ("WBEV1", 2)}
    name, fbyte = names[framing]
    return (b"WB-AAD\x00" + b"\x01" + lp(name) + lp("sym-v1") + u32(1)
            + lp(key_id) + bytes([fbyte]) + b"\x00" + b"\x00")

def open_envelope(env_dict, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = base64.b64decode(env_dict["nonce"])
    tag = base64.b64decode(env_dict["authTag"])
    ct = base64.b64decode(env_dict["ciphertext"])
    kid = env_dict["keyId"]
    results = []
    for framing in ("field", "file"):
        try:
            pt = AESGCM(key).decrypt(nonce, ct + tag, build_aad(kid, framing))
            return pt, framing
        except Exception:
            pass
    try:
        return AESGCM(key).decrypt(nonce, ct + tag, None), "no-aad"
    except Exception:
        return None, None

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    payload = json.load(open(here + "/wb-key-payload.json"))
    if payload.get("keyHex"):
        key = bytes.fromhex(payload["keyHex"])
    else:
        key = hashlib.sha256(payload["secretB64"].encode()).digest()
    print("protector keyId =", hashlib.sha256(key).hexdigest()[:16], "(应为 9127dea1b44020a7)")

    auth = json.load(open(AUTH, encoding="utf8"))
    at = auth["auth"]["accessToken"]
    if not isinstance(at, dict) or not at.get("$wbEncrypted"):
        print("accessToken 不是信封，无需解密")
        return
    env = json.loads(base64.b64decode(at["envelope"]))
    pt, framing = open_envelope(env, key)
    if pt is None:
        print("解密失败: 两种 framing 均不匹配")
        sys.exit(1)
    s = pt.decode("utf-8", "replace")
    print("解密成功 (framing=%s), 明文长度=%d, 是JWT=%s" % (framing, len(pt), s.startswith("eyJ")))
    if s.startswith("eyJ"):
        p2 = s.split(".")[1]
        claims = json.loads(base64.b64decode(p2 + "=" * (-len(p2) % 4)))
        print("iss =", claims.get("iss"))
        print("sub 前8 =", str(claims.get("sub"))[:8], "| 主文件账号 uid 前8 =", auth["account"]["uid"][:8])
        print("exp =", claims.get("exp"), "=>", time.strftime("%Y-%m-%d %H:%M", time.localtime(claims.get("exp", 0))))

    # 顺带验证 keyblob 槽位（file framing）
    try:
        kb = json.load(open(KEYBLOB, encoding="utf8"))
        slot = kb["slots"][0]
        inner = json.loads(base64.b64decode(slot["wrapped"]))
        mk, f2 = open_envelope(inner, key)
        if mk and len(mk) == 32:
            print("keyblob 主密钥解包成功 (framing=%s), masterKeyId = %s (keyblob.keyId=%s)"
                  % (f2, hashlib.sha256(mk).hexdigest()[:16], kb["keyId"]))
    except Exception as e:
        print("keyblob 验证跳过:", e)

if __name__ == "__main__":
    main()
