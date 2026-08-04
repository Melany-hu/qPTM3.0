#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML文件下载链接提取脚本
用于从HTML文件中提取class="fileLink"的下载链接
"""

import os
import re
import argparse
from html.parser import HTMLParser


class FileLinkParser(HTMLParser):
    """HTML解析器，用于提取class="fileLink"的链接"""
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.is_file_link = False
    
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            # 重置标志
            self.is_file_link = False
            self.current_href = None
            
            # 检查属性
            attrs_dict = dict(attrs)
            if 'href' in attrs_dict:
                self.current_href = attrs_dict['href']
                # 检查class属性
                if 'class' in attrs_dict and 'fileLink' in attrs_dict['class']:
                    self.is_file_link = True
    
    def handle_endtag(self, tag):
        if tag == 'a' and self.is_file_link and self.current_href:
            self.links.append(self.current_href)
            self.is_file_link = False
            self.current_href = None

def extract_jpost_links(html_file_path):
    """
    从HTML文件中提取所有class="fileLink"的下载链接
    
    Args:
        html_file_path: HTML文件路径
    
    Returns:
        list: 提取到的下载链接列表
    """
    try:
        # 读取HTML文件
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 使用自定义解析器提取链接
        parser = FileLinkParser()
        parser.feed(html_content)
        
        return parser.links
        
    except Exception as e:
        print(f"处理文件时出错: {e}")
        return []


def save_links_to_file(links, output_file_path):
    """
    将链接保存到文件中
    
    Args:
        links: 链接列表
        output_file_path: 输出文件路径
    """
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link + '\n')
        print(f"已成功保存 {len(links)} 个链接到 {output_file_path}")
    except Exception as e:
        print(f"保存链接时出错: {e}")


def main():
    """
    主函数，处理命令行参数并执行提取操作
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='从HTML文件中提取class="fileLink"的下载链接')
    parser.add_argument('html_file', help='HTML文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')
    args = parser.parse_args()
    
    # 验证输入文件是否存在
    if not os.path.isfile(args.html_file):
        print(f"错误: 文件 {args.html_file} 不存在")
        return
    
    # 提取链接
    print(f"正在从 {args.html_file} 中提取下载链接...")
    links = extract_jpost_links(args.html_file)
    
    # 去重
    unique_links = list(set(links))
    
    # 确定输出文件路径
    if args.output:
        output_file = args.output
    else:
        # 默认输出文件名：原文件名去掉.html后缀，加上_urls_{链接数量}.txt
        base_name = os.path.splitext(os.path.basename(args.html_file))[0]
        url_count = len(unique_links)
        output_file = os.path.join(os.path.dirname(args.html_file), f"{base_name}_urls_{url_count}.txt")
    
    # 保存链接
    if unique_links:
        print(f"总共找到 {len(links)} 个链接")
        save_links_to_file(unique_links, output_file)
    else:
        print("未找到任何下载链接")


if __name__ == "__main__":
    main()
