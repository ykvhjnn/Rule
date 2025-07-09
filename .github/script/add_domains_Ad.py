import sys
import time
import os
import requests
from typing import Set, List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re

class ConfigManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_time = 3600  # 缓存时间1小时
        
        self.url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    def validate_urls(self, urls: List[str]) -> List[str]:
        valid_urls = []
        for url in urls:
            url = url.strip()
            if self.url_pattern.match(url):
                valid_urls.append(url)
            else:
                log(f"无效的URL格式: {url}", major=True)
        return valid_urls

    def get_cache_path(self, url: str) -> Path:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.cache"

    def load_from_cache(self, url: str) -> Optional[Set[str]]:
        cache_file = self.get_cache_path(url)
        if not cache_file.exists():
            return None
            
        try:
            cache_data = json.loads(cache_file.read_text(encoding='utf-8'))
            if time.time() - cache_data['timestamp'] > self.cache_time:
                return None
            return set(cache_data['data'])
        except Exception as e:
            log(f"读取缓存失败 {url}: {str(e)}")
            return None

    def save_to_cache(self, url: str, data: Set[str]):
        try:
            cache_data = {
                'timestamp': time.time(),
                'data': list(data)
            }
            cache_file = self.get_cache_path(url)
            cache_file.write_text(json.dumps(cache_data), encoding='utf-8')
        except Exception as e:
            log(f"保存缓存失败 {url}: {str(e)}")

class AddRuleProcessor:
    def __init__(self, config_urls: Dict[str, List[str]], max_workers: int = 5):
        self.config_urls = config_urls
        self.max_workers = max_workers
        self.config_manager = ConfigManager()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.ADD_DOMAIN: Set[str] = set()

    def fetch_url(self, url: str) -> Set[str]:
        cached_data = self.config_manager.load_from_cache(url)
        if cached_data is not None:
            log(f"从缓存加载配置 {url}")
            return cached_data

        try:
            response = requests.get(url.strip(), headers=self.headers, timeout=10)
            response.raise_for_status()
            rules = {
                line.strip().strip('|@^') 
                for line in response.text.splitlines() 
                if line.strip() and not line.strip().startswith('#')
            }
            
            self.config_manager.save_to_cache(url, rules)
            log(f"从 {url} 成功获取 {len(rules)} 条规则")
            return rules
            
        except Exception as e:
            log(f"从 {url} 获取配置失败: {str(e)}", major=True)
            return set()

    def load_configurations(self):
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {}
            
            for url in self.config_urls.get("ADD_DOMAIN", []):
                if url := url.strip():
                    future = executor.submit(self.fetch_url, url)
                    future_to_url[future] = url
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    rules = future.result()
                    self.ADD_DOMAIN.update(rules)
                except Exception as e:
                    log(f"处理配置失败 {url}: {str(e)}", major=True)

        log(f"配置加载完成：ADD_DOMAIN: {len(self.ADD_DOMAIN)} 条", major=True)

    def process_file(self, input_file: str):
        if not os.path.exists(input_file):
            log(f"文件不存在: {input_file}", major=True)
            return

        log(f"开始处理: {input_file} (文件大小: {os.path.getsize(input_file)/1024/1024:.2f}MB)", major=True)
        output_file = f"{input_file}.processed"
        temp_file = f"{input_file}.temp"
        line_count = kept_count = 0

        try:
            with open(input_file, "r", encoding="utf-8") as fin, \
                 open(temp_file, "w", encoding="utf-8") as fout:

                # 首先写入所有要添加的域名
                for domain in sorted(self.ADD_DOMAIN):
                    fout.write(f"{domain}\n")
                    kept_count += 1

                # 然后写入原文件中的域名（去重）
                seen_domains = set(self.ADD_DOMAIN)
                for line in fin:
                    line_count += 1
                    domain = line.strip()
                    
                    if not domain or domain.startswith("#") or domain in seen_domains:
                        continue

                    seen_domains.add(domain)
                    fout.write(f"{domain}\n")
                    kept_count += 1

                    if line_count % 100000 == 0:
                        log(f"已处理 {line_count} 行, 保留 {kept_count} 条规则")

            os.replace(temp_file, output_file)
            os.replace(output_file, input_file)
            
        except Exception as e:
            log(f"处理失败: {str(e)}", major=True)
            for f in [temp_file, output_file]:
                if os.path.exists(f):
                    os.remove(f)
            return

        log(f"处理完成: 总行数={line_count}, 保留规则={kept_count}", major=True)

def log(event: str, major: bool = False):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[IMPORTANT] " if major else ""
    print(f"[{timestamp}] {prefix}{event}", flush=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: python add_domains.py <filename>")
        sys.exit(1)

    config_urls = {
        "ADD_DOMAIN": ["https://raw.githubusercontent.com/ykvhjnn/Rules/refs/heads/main/Add/Ad.txt"]       # 添加ADD_DOMAIN配置链接
    }

    try:
        processor = AddRuleProcessor(config_urls)
        processor.load_configurations()
        processor.process_file(sys.argv[1])
    except KeyboardInterrupt:
        log("程序被用户中断", major=True)
        sys.exit(1)
    except Exception as e:
        log(f"程序执行出错: {str(e)}", major=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
