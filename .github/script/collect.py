#!/usr/bin/env python3
"""
用法：python domain_cleaner.py <filename>
"""
import re
import sys
import time
import os
import multiprocessing as mp
from typing import Generator, Set, List, Optional

# ========================
# 全局配置
# ========================
CHUNK_SIZE = 100_000  # 每个处理批次的行数 (根据内存调整)
MAX_DOMAIN_LENGTH = 253  # RFC标准域名最大长度
WORKER_COUNT = max(4, mp.cpu_count())  # 并行工作进程数

# 域名正则
DOMAIN_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", 
    re.IGNORECASE
)
# Adblock正则
ADBLOCK_PURE_PATTERN = re.compile(r"^\|\|([a-z0-9\-\.]+)\^$", re.IGNORECASE)
# Clash正则
CLASH_RULE_PREFIX = re.compile(r"^(DOMAIN,|DOMAIN-SUFFIX,)", re.IGNORECASE)

# ========================
# 日志系统
# ========================
def log_event(message: str, is_critical: bool = False) -> None:
    """记录带时间戳和状态标记的日志"""
    timestamp = time.strftime("%H:%M:%S")
    prefix = "![CRIT] " if is_critical else "[INFO] "
    print(f"{timestamp}{prefix}{message}", flush=True)

# ========================
# 核心处理函数
# ========================
def is_valid_domain(domain: str) -> bool:
    """
    严格验证域名格式 (RFC标准)
    规则：
      1. 总长度 <= 253字符
      2. 标签长度 1-63字符
      3. 只包含字母/数字/连字符
      4. TLD至少2个字母
    """
    if len(domain) > MAX_DOMAIN_LENGTH:
        return False
    
    labels = domain.split('.')
    if len(labels) < 2 or len(labels[-1]) < 2:  # TLD检查
        return False
    
    return all(
        1 <= len(label) <= 63 and 
        label[0] != '-' and 
        label[-1] != '-' and 
        all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in label.lower())
        for label in labels
    )

def extract_domain(line: str) -> Optional[str]:
    """
    从文本行提取标准化域名 (支持多格式)
    支持格式：
      1. Adblock格式: ||example.com^
      2. Clash格式: DOMAIN,example.com
      3. ClashMeta.txt格式: +.example.com
      4. 纯域名: example.com
    """
    line = line.strip()
    
    # 1. 处理Adblock格式
    if match := ADBLOCK_PURE_PATTERN.match(line):
        domain = match.group(1)
        return domain.lower() if is_valid_domain(domain) else None
    
    # 2. 处理Clash规则
    if match := CLASH_RULE_PREFIX.match(line):
        parts = line.split(",", 1)
        domain = parts[1].strip() if len(parts) > 1 else ""
        return domain.lower() if is_valid_domain(domain) else None
    
    # 3. 处理通配符
    if line.startswith(("*.", "+.")):
        domain = line[2:].strip()
        return domain.lower() if is_valid_domain(domain) else None
    
    # 4. 处理纯域名
    return line.lower() if is_valid_domain(line) else None

# ========================
# 并行处理框架
# ========================
def process_chunk(chunk: List[str]) -> Set[str]:
    """处理数据块并返回唯一域名集合"""
    local_seen = set()
    for line in chunk:
        if domain := extract_domain(line.strip()):
            local_seen.add(domain)
    return local_seen

def parallel_processor(lines: List[str]) -> Generator[str, None, None]:
    """
    并行处理流水线
    步骤：
      1. 将数据分块
      2. 多进程并行处理
      3. 全局合并结果
    """
    global_seen = set()
    
    # 分块处理
    chunks = [
        lines[i : i + CHUNK_SIZE] 
        for i in range(0, len(lines), CHUNK_SIZE)
    ]
    
    log_event(f"开始并行处理: {len(chunks)} 个数据块 | 每块 {CHUNK_SIZE} 行")
    
    # 并行处理
    with mp.Pool(processes=WORKER_COUNT) as pool:
        results = pool.imap_unordered(process_chunk, chunks)
        
        # 处理进度跟踪
        processed_chunks = 0
        total_chunks = len(chunks)
        
        for result in results:
            processed_chunks += 1
            if processed_chunks % max(1, total_chunks // 10) == 0:  # 每10%进度报告
                log_event(f"处理进度: {processed_chunks}/{total_chunks} 块 ({processed_chunks/total_chunks:.0%})")
                
            for domain in result:
                if domain not in global_seen:
                    global_seen.add(domain)
                    yield domain

# ========================
# 文件处理与安全控制
# ========================
def process_large_file(input_path: str) -> None:
	
    # 阶段1: 文件读取
    log_event(f"开始处理: {os.path.basename(input_path)}", is_critical=True)
    start_time = time.time()
    
    try:
        line_count = 0
        with open(input_path, "r", encoding="utf-8") as f:
            lines = []
            for line in f:
                line_count += 1
                lines.append(line)
                
        log_event(f"已读取: {line_count:,} 行 | 内存使用: {sys.getsizeof(lines)/1024/1024:.2f} MB")
    except Exception as e:
        log_event(f"文件读取失败: {str(e)}", is_critical=True)
        return

    # 阶段2: 并行处理
    temp_path = f"{input_path}.tmp"
    domain_count = 0
    process_start = time.time()
    
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            for domain in parallel_processor(lines):
                f.write(f"{domain}\n")
                domain_count += 1
    except Exception as e:
        log_event(f"处理失败: {str(e)}", is_critical=True)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return
    
    # 阶段3: 原子替换
    try:
        os.replace(temp_path, input_path)
        total_time = time.time() - start_time
        process_time = time.time() - process_start
        
        log_event(
            f"完成: 提取 {domain_count:,} 个域名 | "
            f"总耗时: {total_time:.2f} 秒 | "
            f"处理速度: {line_count/process_time:,.0f} 行/秒",
            is_critical=True
        )
    except Exception as e:
        log_event(f"文件替换失败: {str(e)}", is_critical=True)
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ========================
# 命令行入口
# ========================
if __name__ == "__main__":
    if len(sys.argv) != 2:
        log_event("错误: 请指定输入文件", is_critical=True)
        log_event("用法: python domain_cleaner.py filename.txt", is_critical=True)
        sys.exit(1)
    
    input_file = sys.argv[1]
    if not os.path.isfile(input_file):
        log_event(f"错误: 文件不存在 '{input_file}'", is_critical=True)
        sys.exit(2)
    
    # 检查文件大小
    file_size = os.path.getsize(input_file)
    if file_size > 1024**3:  # >1GB
        log_event(f"警告: 处理大文件 ({file_size/1024/1024:.2f} MB)，请确保足够内存", is_critical=True)
    
    process_large_file(input_file)
