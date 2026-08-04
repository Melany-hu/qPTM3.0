# get_url.py 用于从 HTML 文件中提取所有下载链接，并保存到文本中，输出文件名改为包含链接数量。以便用于IDM下载。

import sys
import os
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

# 默认BASE_URL，仅在无法从HTML提取时使用
BASE_URL_DEFAULT = "https://ftp.pride.ebi.ac.uk/pride/data/archive/2022/10/PXD034183/"
# 固定的PRIDE FTP基础URL
PRIDE_FTP_BASE = "https://ftp.pride.ebi.ac.uk"


class AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.title = None
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            if tag.lower() == "title":
                self.in_title = True
            return
        href = None
        for k, v in attrs:
            if k.lower() == "href":
                href = v
                break
        if not href:
            return
        self.hrefs.append(href)
    
    def handle_data(self, data):
        if self.in_title:
            self.title = data
            self.in_title = False
    
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False


def extract_base_url_from_title(title_text):
    """
    从HTML title中提取基础URL路径
    标题格式通常为: "Index of /pride/data/archive/2022/10/PXD034183"
    """
    if not title_text:
        return None
    
    # 使用正则表达式提取路径部分
    match = re.search(r'Index of (.+)', title_text)
    if match:
        path = match.group(1).strip()
        # 确保路径以/结尾
        if not path.endswith('/'):
            path = path + '/'
        # 组合成完整的BASE_URL
        return PRIDE_FTP_BASE + path
    
    return None

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("用法: python3 get_url.py /path/to/your.html [BASE_URL]", file=sys.stderr)
        print("示例: python3 get_url.py /path/to/your.html", file=sys.stderr)
        sys.exit(1)

    html_path = sys.argv[1]
    
    # 首先尝试从HTML文件中读取内容并提取title
    content = None
    extracted_base_url = None
    
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # 创建解析器实例并提取title
        parser = AnchorCollector()
        parser.feed(content)
        
        # 尝试从title提取BASE_URL
        if parser.title:
            extracted_base_url = extract_base_url_from_title(parser.title)
            if extracted_base_url:
                print(f"从HTML title提取的BASE_URL: {extracted_base_url}")
            else:
                print(f"无法从title提取路径: {parser.title}")
    except Exception as e:
        print(f"读取HTML文件或提取title时出错: {e}")
    
    # 确定使用的base_url: 命令行参数 > 提取的URL > 默认URL
    if len(sys.argv) == 3:
        base_url = sys.argv[2]
        print(f"使用命令行参数指定的BASE_URL: {base_url}")
    elif extracted_base_url:
        base_url = extracted_base_url
    else:
        base_url = BASE_URL_DEFAULT
        print(f"使用默认BASE_URL: {base_url}")
    
    # 如果还没有解析器实例，创建一个新的
    if 'parser' not in locals():
        if content is None:
            with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        parser = AnchorCollector()
        parser.feed(content)

    seen = set()
    results = []
    for href in parser.hrefs:
        h = href.strip()
        if not h or h.startswith("?"):
            continue
        if h.startswith("/"):
            continue
        lower = h.lower()
        if lower.startswith("javascript:") or lower.startswith("mailto:"):
            continue

        abs_url = urljoin(base_url, h)
        if abs_url not in seen:
            seen.add(abs_url)
            results.append(abs_url)

    # 保存到以输入 HTML 名称为前缀，带链接数量的文件
    base_stem = os.path.splitext(os.path.basename(html_path))[0]
    link_count = len(results)
    out_file = f"{base_stem}_urls_{link_count}.txt"
    with open(out_file, "w", encoding="utf-8") as out_f:
        for url in results:
            out_f.write(url + "\n")

    # 输出
    for url in results:
        print(url)

if __name__ == "__main__":
    main()