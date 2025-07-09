#!/bin/bash
# =============================================================================
# 通用规则生成脚本，支持多种规则类型（如 Proxy、Directfix、Ad、自定义等）
# 用法示例：bash build-rules.sh Proxy|Directfix|Ad|自定义组名
# =============================================================================

set -euo pipefail   # 严格模式：遇到错误立即退出，变量未定义即报错

# -----------------------------------------------------------------------------
# 【步骤1】错误输出与退出函数
# -----------------------------------------------------------------------------
function error_exit() {
    echo "[$(date '+%H:%M:%S')] [ERROR] $1" >&2
    exit 1
}

# -----------------------------------------------------------------------------
# 【步骤2】参数检查，必须指定规则类型（组名）
# -----------------------------------------------------------------------------
if [[ $# -ne 1 ]]; then
    echo "[$(date '+%H:%M:%S')] 用法: $0 [组名]"
    echo "示例: $0 Proxy"
    exit 1
fi

# -----------------------------------------------------------------------------
# 【步骤3】进入脚本目录，确保相对路径正确
# -----------------------------------------------------------------------------
cd "$(cd "$(dirname "$0")"; pwd)" || error_exit "无法进入脚本目录"

# -----------------------------------------------------------------------------
# 【步骤4】全部规则源组定义（可自定义扩展组名及规则url）
# -----------------------------------------------------------------------------
declare -A urls_map

urls_map["Proxy"]="
https://ruleset.skk.moe/Clash/domainset/speedtest.txt
https://ruleset.skk.moe/Clash/non_ip/my_proxy.txt
https://ruleset.skk.moe/Clash/non_ip/ai.txt
https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Clash/GitHub/GitHub.list
https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-ruleset/proxy.list
https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Clash/Global/Global_Domain_For_Clash.txt
https://raw.githubusercontent.com/ykvhjnn/Rules/refs/heads/main/Add/Proxy.txt
"

urls_map["Directfix"]="
https://ruleset.skk.moe/Clash/non_ip/microsoft_cdn.txt
https://ruleset.skk.moe/Clash/non_ip/lan.txt
https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-ruleset/private.list
https://raw.githubusercontent.com/ykvhjnn/Rules/refs/heads/main/Add/Direct.txt
"

urls_map["Ad"]="
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/doh.txt
https://raw.githubusercontent.com/ghvjjjj/adblockfilters/refs/heads/main/rules/adblockdomainlite.txt
https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockdomainlite.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.mini.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.xiaomi.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.oppo-realme.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.vivo.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.samsung.txt
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.huawei.txt
https://raw.githubusercontent.com/ykvhjnn/Rules/refs/heads/main/Add/Ad.txt
"

urls_map["Direct"]="
https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Clash/China/China_Domain_For_Clash.txt
"

# -----------------------------------------------------------------------------
# 【步骤5】各组对应的 Python 清洗脚本列表（组名一一对应）
# -----------------------------------------------------------------------------
declare -A py_scripts
py_scripts["Proxy"]="collect.py remove_domains_Proxy.py clean.py"
py_scripts["Directfix"]="collect.py clean.py"
py_scripts["Ad"]="collect.py remove_domains_Ad.py clean.py add_domains_Ad.py"
py_scripts["Direct"]="collect.py clean.py"

# -----------------------------------------------------------------------------
# 【步骤6】参数校验，必须是已定义组名
# -----------------------------------------------------------------------------
group="$1"
if [[ -z "${urls_map[$group]:-}" ]]; then
    echo "[$(date '+%H:%M:%S')] [ERROR] 未找到组: $group"
    echo "可用组有:"
    for k in "${!urls_map[@]}"; do
        echo "  - $k"
    done
    exit 1
fi

# -----------------------------------------------------------------------------
# 【步骤7】相关文件名变量定义
# -----------------------------------------------------------------------------
domain_file="${group}_domain.txt"
tmp_file="${group}_tmp.txt"
mihomo_txt_file="${group}_Mihomo.txt"
mihomo_mrs_file="${mihomo_txt_file%.txt}.mrs"
clash_file="${group}_clash.txt"
adblock_file="${group}_adblock.txt"
singbox_file="${group}_singbox.json"  # sing-box json格式文件名
singbox_srs_file="${group}_singbox.srs"  # sing-box srs格式文件名

# -----------------------------------------------------------------------------
# 【步骤8】下载 Mihomo 和 sing-box 工具（只下载一次，已存在则跳过）
# -----------------------------------------------------------------------------
MIHOMO_TOOL=".mihomo_tool"
SINGBOX_TOOL=".singbox_tool"

function download_mihomo() {
    if [[ -f "$MIHOMO_TOOL" && -x "$MIHOMO_TOOL" ]]; then
        echo "[$(date '+%H:%M:%S')] Mihomo 工具已存在，跳过下载"
        return
    fi
    echo "[$(date '+%H:%M:%S')] 开始下载 Mihomo 工具..."
    wget -q https://github.com/MetaCubeX/mihomo/releases/download/Prerelease-Alpha/version.txt \
        || error_exit "下载 Mihomo 版本文件失败"
    version=$(cat version.txt)
    tool_name="mihomo-linux-amd64-$version"
    wget -q "https://github.com/MetaCubeX/mihomo/releases/download/Prerelease-Alpha/$tool_name.gz" \
        || error_exit "下载 Mihomo 工具失败"
    gzip -d "$tool_name.gz" || error_exit "解压 Mihomo 工具失败"
    chmod +x "$tool_name" || error_exit "赋予 Mihomo 工具可执行权限失败"
    mv "$tool_name" "$MIHOMO_TOOL"
    rm -f version.txt
}

function download_singbox() {
    if [[ -f "$SINGBOX_TOOL" && -x "$SINGBOX_TOOL" ]]; then
        echo "[$(date '+%H:%M:%S')] sing-box 工具已存在，跳过下载"
        return
    fi
    echo "[$(date '+%H:%M:%S')] 开始下载 sing-box 工具..."
    
    # 获取最新的sing-box版本
    latest_version=$(curl -s "https://api.github.com/repos/SagerNet/sing-box/releases/latest" | grep -Po '"tag_name": "\K.*?(?=")')
    if [[ -z "$latest_version" ]]; then
        error_exit "获取 sing-box 版本失败"
    fi
    
    # 下载sing-box工具
    wget -q "https://github.com/SagerNet/sing-box/releases/download/${latest_version}/sing-box-${latest_version#v}-linux-amd64.tar.gz" \
        || error_exit "下载 sing-box 工具失败"
    
    tar xzf "sing-box-${latest_version#v}-linux-amd64.tar.gz" \
        || error_exit "解压 sing-box 工具失败"
    
    mv "sing-box-${latest_version#v}-linux-amd64/sing-box" "$SINGBOX_TOOL" \
        || error_exit "移动 sing-box 工具失败"
    
    chmod +x "$SINGBOX_TOOL" || error_exit "赋予 sing-box 工具可执行权限失败"
    
    # 清理临时文件
    rm -rf "sing-box-${latest_version#v}-linux-amd64" "sing-box-${latest_version#v}-linux-amd64.tar.gz"
}

download_mihomo
download_singbox

# -----------------------------------------------------------------------------
# 【步骤9】清理旧临时文件，防止数据混杂
# -----------------------------------------------------------------------------
> "$domain_file"
> "$tmp_file"

# -----------------------------------------------------------------------------
# 【步骤10】并发批量下载规则源，合并到临时文件
# -----------------------------------------------------------------------------
echo "[$(date '+%H:%M:%S')] 开始并发下载规则源..."

urls_list=()
while read -r url; do
    [[ -n "$url" ]] && urls_list+=("$url")
done <<< "${urls_map[$group]}"

for url in "${urls_list[@]}"; do
    {
        out="${tmp_file}_$RANDOM"
        if curl --http2 --compressed --max-time 30 --retry 2 -sSL "$url" >> "$out"; then
            echo "[$(date '+%H:%M:%S')] [小] 拉取成功: $url"
        else
            echo "[$(date '+%H:%M:%S')] [WARN] 拉取失败: $url" >&2
        fi
    } &
    if [[ $(jobs -rp | wc -l) -ge 8 ]]; then
        wait -n
    fi
done
wait
cat "${tmp_file}"_* >> "$tmp_file" 2>/dev/null || true
rm -f "${tmp_file}"_*

echo "[$(date '+%H:%M:%S')] 规则源全部下载合并完成"

# -----------------------------------------------------------------------------
# 【步骤11】合并临时文件到主文件并清理换行符
# -----------------------------------------------------------------------------
cat "$tmp_file" >> "$domain_file"
rm -f "$tmp_file"
sed -i 's/\r//' "$domain_file"

# -----------------------------------------------------------------------------
# 【步骤12】依次执行对应 Python 清洗脚本
# -----------------------------------------------------------------------------
for py in ${py_scripts[$group]}; do
    if [[ ! -f "$py" ]]; then
        error_exit "找不到 Python 脚本: $py"
    fi
    echo "[$(date '+%H:%M:%S')] 执行脚本: $py"
    if ! python "$py" "$domain_file"; then
        error_exit "Python 脚本 $py 执行失败"
    fi
done

# -----------------------------------------------------------------------------
# 【步骤13】统计最终规则数量，排除空行与注释
# -----------------------------------------------------------------------------
rule_count=$(grep -vE '^\s*$|^#' "$domain_file" | wc -l)
echo "[$(date '+%H:%M:%S')] 文件: $mihomo_txt_file, $mihomo_mrs_file, $singbox_file, $singbox_srs_file"
echo "[$(date '+%H:%M:%S')] 规则总数: $rule_count"

# -----------------------------------------------------------------------------
# 【步骤14】格式化输出，全部加前缀 +.
# -----------------------------------------------------------------------------
sed "s/^/\+\./g" "$domain_file" > "$mihomo_txt_file"

# -----------------------------------------------------------------------------
# 【步骤15】调用 Mihomo 工具转换为mrs格式
# -----------------------------------------------------------------------------
if ! "./$MIHOMO_TOOL" convert-ruleset domain text "$mihomo_txt_file" "$mihomo_mrs_file"; then
    error_exit "Mihomo 工具转换 $mihomo_txt_file 失败"
fi

# -----------------------------------------------------------------------------
# 【步骤16】生成 Clash、Adblock 和 Sing-box 格式
# -----------------------------------------------------------------------------
# 生成 Clash 格式
awk '!/^(\s*$|#)/{gsub(/^[ \t]*/,"");gsub(/[ \t]*$/,""); print "DOMAIN-SUFFIX,"$0}' "$domain_file" > "$clash_file"

# 生成 Adblock 格式
awk '!/^(\s*$|#)/{gsub(/^[ \t]*/,"");gsub(/[ \t]*$/,""); print "||"$0"^"}' "$domain_file" > "$adblock_file"

# 生成 sing-box 1.12.x json 格式
{
    echo "{"
    echo "  \"version\": 3,"
    echo "  \"rules\": ["
    echo "    {"
    echo "      \"domain_suffix\": ["
    # 处理domain文件,生成json数组格式的域名列表
    awk -v group="$group" '
    BEGIN {first=1}
    !/^(\s*$|#)/ {
        gsub(/^[ \t]*/,"")
        gsub(/[ \t]*$/,"")
        if (!first) printf ",\n"
        printf "        \"%s\"", $0
        first=0
    }' "$domain_file"
    echo
    echo "      ]"
    echo "    }"
    echo "  ]"
    echo "}"
} > "$singbox_file"

# -----------------------------------------------------------------------------
# 【步骤17】使用sing-box工具转换为srs格式
# -----------------------------------------------------------------------------
# 修正: 使用正确的命令行参数格式
if ! "./$SINGBOX_TOOL" rule-set compile "$singbox_file" -o "$singbox_srs_file"; then
    error_exit "sing-box 工具转换 $singbox_file 失败"
fi

# -----------------------------------------------------------------------------
# 【步骤18】整理输出文件夹并清理临时文件
# -----------------------------------------------------------------------------
repo_root="$(cd ../.. && pwd)"
mkdir -p "$repo_root/txt" "$repo_root/mrs" "$repo_root/domain" "$repo_root/clash" "$repo_root/adblock" "$repo_root/singbox" "$repo_root/srs" "$repo_root/.cache"

mv "$mihomo_txt_file" "$repo_root/txt/$mihomo_txt_file"
mv "$mihomo_mrs_file" "$repo_root/mrs/$mihomo_mrs_file"
mv "$domain_file" "$repo_root/domain/$domain_file"
mv "$clash_file" "$repo_root/clash/$clash_file"
mv "$adblock_file" "$repo_root/adblock/$adblock_file"
mv "$singbox_file" "$repo_root/singbox/$singbox_file"
mv "$singbox_srs_file" "$repo_root/srs/$singbox_srs_file"

rm -f "${group}_tmp.txt"

echo "[$(date '+%H:%M:%S')] [完成] $group 规则生成并清理完毕"
