#!/usr/bin/env python3
"""
从ProteomeXchange XML文件中提取下载链接
"""

import xml.etree.ElementTree as ET
import sys
import os


def extract_download_urls(xml_file):
    """
    从XML文件中提取所有下载链接
    
    Args:
        xml_file: XML文件路径
        
    Returns:
        list: 包含所有下载链接的列表
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        urls = []
        
        # 提取所有文件下载链接（不包括数据集URI，只提取实际文件下载链接）
        dataset_files = root.findall('.//DatasetFile')
        for file_elem in dataset_files:
            file_name = file_elem.get('name', 'Unknown')
            
            # 查找所有包含URI的cvParam元素
            # MS:1002849 = Search engine output file URI
            # MS:1002846 = Associated raw file URI
            # 也尝试查找所有包含"URI"的cvParam元素，以支持其他可能的URI类型
            cv_params = file_elem.findall('.//cvParam[@accession="MS:1002849"]')
            cv_params.extend(file_elem.findall('.//cvParam[@accession="MS:1002846"]'))
            
            # 如果没找到，尝试查找所有包含URI的cvParam（更通用的方法）
            if not cv_params:
                all_params = file_elem.findall('.//cvParam')
                cv_params = [p for p in all_params if 'URI' in p.get('name', '') and p.get('value')]
            
            for param in cv_params:
                url = param.get('value')
                if url and url.startswith('http'):  # 确保是有效的HTTP链接
                    urls.append((file_name, url))
        
        return urls
    
    except ET.ParseError as e:
        print(f"XML解析错误: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return []


def main():
    if len(sys.argv) < 2:
        print("用法: python extract_urls_from_xml.py <xml_file>")
        print("示例: python extract_urls_from_xml.py PX_IPX0003286000.xml")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    
    if not os.path.exists(xml_file):
        print(f"错误: 文件 '{xml_file}' 不存在", file=sys.stderr)
        sys.exit(1)
    
    urls = extract_download_urls(xml_file)
    
    if not urls:
        print("未找到任何下载链接")
        return
    
    # 输出结果
    print(f"找到 {len(urls)} 个下载链接:\n")
    print("=" * 80)
    
    for i, (name, url) in enumerate(urls, 1):
        print(f"{i}. {name}")
        print(f"   {url}\n")
    
    # 保存到文件（只保存链接，每行一个）
    url_count = len(urls)
    # 获取输入文件的目录和基础文件名
    xml_dir = os.path.dirname(os.path.abspath(xml_file))
    xml_basename = os.path.basename(xml_file)
    base_name, ext = os.path.splitext(xml_basename)
    
    # 生成输出文件名，保存在与输入文件相同的目录
    output_file = os.path.join(xml_dir, f"{base_name}_urls_{url_count}.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        for name, url in urls:
            f.write(f"{url}\n")
    
    print(f"\n链接已保存到: {output_file} (共 {url_count} 个链接)")


if __name__ == "__main__":
    main()

