#!/usr/bin/env python3
"""根据 PDC ID 提取 Raw Mass Spectra (Proprietary) 下载链接。"""

import requests, time

GRAPHQL_URL = 'https://pdc.cancer.gov/graphql'


def gql(query, retries=3):
    for i in range(retries):
        try:
            r = requests.post(GRAPHQL_URL, json={'query': query}, timeout=60)
            r.raise_for_status()
            d = r.json()
            if 'errors' in d:
                print(f"  GraphQL 错误: {d['errors']}")
                return None
            return d
        except Exception as e:
            print(f"  查询失败 ({i+1}/{retries}): {e}")
            if i < retries - 1:
                time.sleep(5)
    return None


def get_raw_urls(pdc_id):
    """返回 (raw_urls_list, study_name)"""

    # 1. 获取 UUID
    print(f"  查找 UUID ...")
    d = gql("""{ studyCatalog { pdc_study_id
        versions { study_id is_latest_version } } }""")
    if not d:
        return []
    uid = None
    for s in d['data']['studyCatalog']:
        if s['pdc_study_id'] == pdc_id:
            for v in s['versions']:
                if v['is_latest_version'] == 'yes':
                    uid = v['study_id']
                    break
    if not uid:
        print(f"  未找到 {pdc_id}")
        return []

    # 2. 翻页获取所有文件
    urls = []
    offset = 0
    while True:
        q = """{ filesPerStudy(study_id: "%s", offset: %d, limit: 200) {
            file_name file_type data_category signedUrl { url }
        }}""" % (uid, offset)
        d = gql(q)
        if not d:
            break
        files = d['data'].get('filesPerStudy', [])
        if not files:
            break
        for f in files:
            if 'Raw Mass Spectra' in f.get('data_category', '') and \
               f.get('file_type') == 'Proprietary':
                su = f.get('signedUrl')
                if isinstance(su, dict) and su.get('url'):
                    urls.append(su['url'])
        print(f"    offset={offset}: {len(files)} files, raw so far: {len(urls)}")
        if len(files) < 200:
            break
        offset += 200
        time.sleep(1)

    return urls


def main():
    import sys

    if len(sys.argv) > 1:
        pdc_ids = sys.argv[1:]
    else:
        pdc_ids = ['PDC000627']

    for pid in pdc_ids:
        print(f"\n{'='*50}")
        print(f"PDC: {pid}")
        print(f"{'='*50}")
        urls = get_raw_urls(pid)
        print(f"共 {len(urls)} 个 Raw Mass Spectra 链接")
        for u in urls:
            print(u)


if __name__ == '__main__':
    main()
