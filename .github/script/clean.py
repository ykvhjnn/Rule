import sys
import asyncio
import traceback
from typing import List, Set, Tuple, Dict, Generator, Optional

# 增强版常用顶级域名列表（500+域名）
COMMON_TLDS = {
    # 通用TLD
    "com", "org", "net", "edu", "gov", "mil", "int", "biz", "info", "name", "pro", 
    "coop", "aero", "museum", "idv", "xyz", "top", "site", "online", "club", "shop", 
    "app", "io", "dev", "art", "inc", "vip", "store", "tech", "blog", "wiki", "link", 
    "live", "news", "run", "fun", "cloud", "one", "world", "group", "life", "today", 
    "agency", "company", "center", "team", "email", "solutions", "network", "systems", 
    "media", "digital", "works", "design", "finance", "plus", "studio", "space", "tv", 
    "mobi", "travel", "games", "social", "tools", "expert", "services", "global", 
    "community", "academy", "consulting", "directory", "events", "foundation", 
    "gallery", "guide", "institute", "management", "marketing", "photos", "reviews", 
    "software", "solutions", "support", "training", "ventures", "vision", "watch",
    
    # 国家和地区TLD
    "cn", "us", "uk", "jp", "de", "fr", "ru", "au", "ca", "br", "it", "es", "nl", 
    "se", "ch", "no", "fi", "be", "at", "dk", "pl", "hk", "tw", "kr", "in", "sg", 
    "cz", "il", "ie", "tr", "za", "mx", "cl", "ar", "nz", "gr", "hu", "pt", "ro", 
    "bg", "sk", "si", "lt", "lv", "ee", "hr", "rs", "ua", "by", "kz", "ge", "md", 
    "ba", "al", "me", "is", "lu", "li", "mt", "cy", "mc", "sm", "ad", "va", "th", 
    "vn", "ph", "my", "id", "eg", "sa", "ae", "qa", "om", "kw", "bh", "jo", "lb", 
    "pk", "bd", "lk", "np", "mm", "kh", "la", "mn", "am", "az", "uz", "kg", "tj",
    
    # 多级TLD
    "com.cn", "net.cn", "gov.cn", "org.cn", "edu.cn", "ac.cn", 
    "bj.cn", "sh.cn", "tj.cn", "cq.cn", "he.cn", "nm.cn", "ln.cn", 
    "jl.cn", "hl.cn", "js.cn", "zj.cn", "ah.cn", "fj.cn", "jx.cn", 
    "sd.cn", "ha.cn", "hb.cn", "hn.cn", "gd.cn", "gx.cn", "hi.cn", 
    "sc.cn", "gz.cn", "yn.cn", "xz.cn", "sn.cn", "gs.cn", "qh.cn", 
    "nx.cn", "xj.cn", "co.uk", "org.uk", "gov.uk", "ac.uk", "sch.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "asn.au", "id.au",
    "co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp", "ed.jp", "gr.jp", "lg.jp",
    "com.hk", "net.hk", "org.hk", "idv.hk", "gov.hk", "edu.hk",
    "co.nz", "ac.nz", "geek.nz", "maori.nz", "net.nz", "org.nz", "school.nz", "govt.nz",
    
    # 国际化域名TLD (IDN)
    "xn--fiqs8s", "xn--fiqz9s", "xn--55qx5d", "xn--io0a7i", "xn--90ais", "xn--j1amh",
    "xn--d1acj3b", "xn--p1ai", "xn--mgbaam7a8h", "xn--ygbi2ammx", "xn--90a3ac",
    
    # 新gTLD
    "ai", "io", "ly", "to", "sh", "ac", "gg", "je", "im", "fm", "am", "cx", "ms", 
    "nu", "sc", "tf", "tk", "wf", "yt", "ovh", "host", "hosting", "server", "cloud", 
    "web", "site", "online", "xyz", "icu", "cyou", "fun", "shop", "store", "sale", 
    "deal", "discount", "market", "blackfriday", "cyber", "network", "free", "best", 
    "top", "win", "bet", "poker", "casino", "bingo", "luxe", "rich", "guru", "expert", 
    "pro", "law", "med", "reit", "church", "faith", "bio", "eco", "green", "organic"
}

def extract_full_tld(parts: List[str]) -> Tuple[List[str], str]:
    if not parts:
        return [], ""
    for i in range(min(5, len(parts)), 0, -1):
        tld_candidate = ".".join(parts[-i:]).lower()
        if tld_candidate in COMMON_TLDS:
            return parts[:-i], tld_candidate
    return parts[:-1], parts[-1].lower()

def get_main_domain(domain: str) -> str:
    parts = domain.strip().split('.')
    if not parts:
        return ""
    rest_parts, _ = extract_full_tld(parts)
    if rest_parts:
        return rest_parts[-1]
    return ""

def domain_sort_key(domain: str) -> Tuple[str, str, Tuple[str, ...]]:
    parts = domain.strip().split('.')
    if not parts:
        return ("", "", ())
    rest_parts, tld = extract_full_tld(parts)
    main_domain = rest_parts[-1] if rest_parts else ""
    sub_parts = tuple(reversed(rest_parts[:-1])) if rest_parts else ()
    return (main_domain, tld, sub_parts)

def normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    domain = domain.strip('.')
    while '..' in domain:
        domain = domain.replace('..', '.')
    return domain

def process_chunk(chunk: List[str]) -> Set[str]:
    """
    处理数据块：规范化和去重
    """
    valid_domains = set()
    for line in chunk:
        domain = normalize_domain(line)
        valid_domains.add(domain)
    return valid_domains

def remove_subdomains(domains: Set[str]) -> Set[str]:
    """
    去除已存在父域名的子域名（如a.example.com若example.com存在则去除a.example.com）
    """
    # 先排序，短的在前
    sorted_domains = sorted(domains, key=lambda d: (len(d.split('.')), d))
    parent_set = set()
    result = set()
    for domain in sorted_domains:
        parts = domain.split('.')
        found_parent = False
        # 从二级开始, 向上查找父域名
        for i in range(1, len(parts)):
            parent = '.'.join(parts[i:])
            if parent in parent_set:
                found_parent = True
                break
        if not found_parent:
            parent_set.add(domain)
            result.add(domain)
    return result

async def read_lines(file_path: str, chunk_size: int = 100000) -> Generator[List[str], None, None]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                lines = f.readlines(chunk_size)
                if not lines:
                    break
                yield lines
    except FileNotFoundError:
        print(f"❌ 错误：文件未找到 - {file_path}")
        raise
    except PermissionError:
        print(f"❌ 错误：无文件访问权限 - {file_path}")
        raise
    except UnicodeDecodeError:
        print(f"❌ 错误：文件编码问题 - {file_path}")
        raise

async def process_file(input_file: str) -> Optional[List[str]]:
    try:
        print(f"🔍 开始处理文件: {input_file}")
        all_domains = set()
        async for chunk in read_lines(input_file):
            chunk_domains = process_chunk(chunk)
            all_domains.update(chunk_domains)
        if not all_domains:
            print("⚠️ 文件为空或无可处理域名")
            return None
        print(f"📊 域名去重前数量: {len(all_domains)}")

        # 去除子域名（父域名存在时）
        all_domains = remove_subdomains(all_domains)
        print(f"📉 域名去除子域名后数量: {len(all_domains)}")

        sorted_domains = sorted(all_domains, key=domain_sort_key)
        print("🔠 域名排序完成")
        return sorted_domains
    except Exception as e:
        print(f"❌ 文件处理错误: {e}")
        traceback.print_exc()
        return None

async def write_output(output_file: str, domains: List[str]) -> bool:
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for domain in domains:
                f.write(f"{domain}\n")
        return True
    except IOError as e:
        print(f"❌ 文件写入错误: {e}")
        traceback.print_exc()
        return False

async def main():
    try:
        if len(sys.argv) < 2:
            print("❌ 请提供输入文件路径作为参数")
            print("用法: python script.py input.txt")
            return
        input_file = sys.argv[1]
        sorted_domains = await process_file(input_file)
        if not sorted_domains:
            return
        if await write_output(input_file, sorted_domains):
            print(f"✅ 处理完成！最终域名数: {len(sorted_domains)}")
            print(f"💾 结果已保存至: {input_file}")
    except Exception as e:
        print(f"❌ 处理过程中发生严重错误: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
