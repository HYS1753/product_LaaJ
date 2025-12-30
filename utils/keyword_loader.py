import pandas as pd
from typing import List

def parse_keywords_from_text(text: str, delimiter: str) -> List[str]:
    '''텍스트에서 키워드 파싱'''
    if delimiter == '\\\\n':
        delimiter = '\\n'
    keywords = [k.strip() for k in text.split(delimiter) if k.strip()]
    return keywords

def parse_keywords_from_file(file, delimiter: str) -> List[str]:
    '''텍스트 파일에서 키워드 파싱'''
    text_content = file.read().decode('utf-8')
    return parse_keywords_from_text(text_content, delimiter)

def parse_keywords_from_csv(file) -> List[str]:
    '''CSV 파일에서 키워드 파싱 (첫 번째 컬럼 사용)'''
    df = pd.read_csv(file)
    keywords = df.iloc[:, 0].astype(str).str.strip().tolist()
    return [k for k in keywords if k and k != 'nan']

def get_keyword_preview(keywords: List[str], limit: int = 10) -> List[str]:
    '''키워드 미리보기'''
    return keywords[:limit]